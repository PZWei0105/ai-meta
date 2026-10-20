"""共用小工具：連線、時間、文字清理、網址正規化。"""
import datetime as dt
import hashlib
import html
import os
import re
import time
import urllib.parse

import requests

UTC = dt.timezone.utc
TW = dt.timezone(dt.timedelta(hours=8))
UA_BROWSER = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/141.0 Safari/537.36')
UA_BOT = 'AIMetaReader/1.0 (personal AI tool tracker; https://github.com/PZWei0105/ai-meta)'


def now() -> dt.datetime:
    return dt.datetime.now(UTC)


def iso(t: dt.datetime) -> str:
    return t.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_iso(s):
    if not s:
        return None
    if isinstance(s, dt.datetime):
        return s if s.tzinfo else s.replace(tzinfo=UTC)
    try:
        return dt.datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)
    except (ValueError, TypeError):
        try:
            t = dt.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
            return t if t.tzinfo else t.replace(tzinfo=UTC)
        except ValueError:
            return None


def hours_since(t: dt.datetime, ref: dt.datetime | None = None) -> float:
    return ((ref or now()) - t).total_seconds() / 3600


def days_since(t, ref=None) -> float:
    t = parse_iso(t)
    return 9999.0 if t is None else hours_since(t, ref) / 24


class Http:
    """所有對外連線都走這裡：固定 User-Agent、逾時、遇到 5xx/429 重試一次。GitHub API 自動帶 token。"""

    def __init__(self):
        self.s = requests.Session()
        self.calls = 0
        self.gh_token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or ''

    def get(self, url, *, bot=False, headers=None, timeout=30, retries=1):
        h = {'User-Agent': UA_BOT if bot else UA_BROWSER, 'Accept': '*/*',
             'Accept-Language': 'en-US,en;q=0.9,zh-TW;q=0.8'}
        if url.startswith('https://api.github.com/') and self.gh_token:
            h['Authorization'] = f'Bearer {self.gh_token}'
            h['Accept'] = 'application/vnd.github+json'
        h.update(headers or {})
        last = None
        for attempt in range(retries + 1):
            self.calls += 1
            try:
                r = self.s.get(url, headers=h, timeout=timeout)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    last = RuntimeError(f'HTTP {r.status_code}')
                    time.sleep(3 + attempt * 4)
                    continue
                return r
            except requests.RequestException as e:
                last = e
                if attempt < retries:
                    time.sleep(3 + attempt * 4)
        raise last

    def text(self, url, **kw) -> str:
        r = self.get(url, **kw)
        if r.status_code != 200:
            raise RuntimeError(f'HTTP {r.status_code}')
        r.encoding = r.encoding if r.encoding and r.encoding.lower() != 'iso-8859-1' else 'utf-8'
        return r.text

    def json(self, url, **kw):
        r = self.get(url, **kw)
        if r.status_code != 200:
            raise RuntimeError(f'HTTP {r.status_code}')
        return r.json()


# ---------- 文字 ----------
_TAG = re.compile(r'<[^>]+>')
_WS = re.compile(r'\s+')
_SCRIPT = re.compile(r'(?is)<(script|style|noscript|svg|figure|figcaption)[^>]*>.*?</\1>')
_CJK = re.compile(r'[㐀-鿿豈-﫿]')


def strip_html(s: str) -> str:
    if not s:
        return ''
    s = _SCRIPT.sub(' ', s)
    s = _TAG.sub(' ', s)
    s = html.unescape(html.unescape(s))
    return _WS.sub(' ', s).replace('\xa0', ' ').strip()


def strip_md(s: str) -> str:
    """把 markdown 變成一行純文字（連結只留文字）。"""
    if not s:
        return ''
    s = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', s)
    s = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'(\*\*|__)(.+?)\1', r'\2', s)
    s = re.sub(r'(?<![\w*])[*_](?=\S)(.+?)(?<=\S)[*_](?![\w*])', r'\1', s)
    s = s.replace('`', '').replace('\\_', '_')
    s = re.sub(r'^[#>\s]+', '', s)
    s = re.sub(r'\s[#>]+\s', ' ', s)
    return _WS.sub(' ', html.unescape(s)).strip()


def cjk_ratio(s: str) -> float:
    if not s:
        return 0.0
    return len(_CJK.findall(s)) / max(1, len(s))


def clip(s: str, n: int) -> str:
    s = (s or '').strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    if cjk_ratio(cut) < 0.3:
        sp = cut.rfind(' ')
        if sp > n * 0.6:
            cut = cut[:sp]
    return cut.rstrip(' ,.;:，。、；：') + '…'


def canon_url(u: str) -> str:
    try:
        p = urllib.parse.urlsplit(u.strip())
    except ValueError:
        return u.strip()
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not re.match(r'^(utm_|fbclid|gclid|ref$|ref_|source$)', k, re.I)]
    netloc = p.netloc.lower()
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    path = p.path.rstrip('/') or '/'
    return urllib.parse.urlunsplit(('https', netloc, path, urllib.parse.urlencode(q), p.fragment))


def sid(s: str, n: int = 12) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:n]
