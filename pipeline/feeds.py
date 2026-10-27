"""官方更新紀錄的解析器：每種頁面格式一個函式，全部輸出同一種「改版項目」。

項目格式：{'src','v','p','d'(YYYY-MM-DD),'t'(英文標題),'b'(英文內文),'url','models':[...]}
"""
import datetime as dt
import json
import re
import urllib.parse

import feedparser
from bs4 import BeautifulSoup

from .util import clip, strip_html, strip_md

MONTHS = {m: i for i, m in enumerate(
    ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october',
     'november', 'december'], 1)}
for _k, _v in list(MONTHS.items()):
    MONTHS[_k[:3]] = _v
MONTHS['sept'] = 9

_RX_MDY = re.compile(r'\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b')
_RX_YMD = re.compile(r'\b(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\b')
_RX_MD = re.compile(r'^\s*([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*$')
_RX_MY = re.compile(r'^\s*([A-Za-z]{3,9}),?\s+(\d{4})\s*$')


def parse_date(s: str, year_hint: int | None = None):
    """支援 'October 16, 2026'、'Oct 16, 2026'、'2026.10.13'、'2026-10-13'、('Oct 16' + 年份提示)。"""
    if not s:
        return None
    s = s.strip()
    m = _RX_MDY.search(s)
    if m and m.group(1).lower() in MONTHS:
        try:
            return dt.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            return None
    m = _RX_YMD.search(s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _RX_MD.match(s)
    if m and year_hint and m.group(1).lower() in MONTHS:
        try:
            return dt.date(year_hint, MONTHS[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            return None
    return None


def first_sentence(s: str, n: int = 110) -> str:
    s = (s or '').strip()
    m = re.match(r'(.{12,}?[.!?])(\s|$)', s)
    out = m.group(1) if m else s
    return clip(out.rstrip('.'), n)


def _item(src, d, title, body, url, models=None):
    title = re.sub(r'\s+', ' ', title or '').strip(' :—-')
    body = re.sub(r'\s+', ' ', body or '').strip()
    if body.lower().startswith(title.lower()):
        body = body[len(title):].lstrip(' :—-.')
    return {'src': src['id'], 'v': src['vendor'], 'p': src['product'], 'd': d.isoformat() if d else None,
            't': clip(title, 160), 'b': clip(body, 900), 'url': url, 'models': models or []}


# ------------------------------------------------------------------ Markdown（依日期分段）
def md_dated(src, text):
    """'## October 13, 2026' 或 '### October 15, 2026' 標題，底下是 * / - 條列（續行縮排、可跨空行）。"""
    base = src.get('link') or src['url'].replace('.md.txt', '').replace('.md', '')
    entries = []
    cur_date, cur, prev_blank = None, None, False

    def push():
        nonlocal cur
        if cur and cur_date:
            entries.append((cur_date, cur))
        cur = None

    for line in text.splitlines():
        h = re.match(r'^#{2,5}\s+(.+?)\s*$', line)
        if h:
            push()
            d = parse_date(h.group(1))
            if d:
                cur_date = d
            elif cur_date:
                cur = f'**{h.group(1)}**'
            prev_blank = False
            continue
        if cur_date is None or line.lstrip().startswith(('<', '</', '>')):
            continue
        b = re.match(r'^[*\-]\s+(.*)', line)
        if b:
            push()
            cur = b.group(1)
        elif not line.strip():
            prev_blank = True
            continue
        elif line.startswith((' ', '\t')):
            cur = (cur + ' ' + line.strip()) if cur else line.strip()
        elif cur is not None and not prev_blank:
            cur += ' ' + line.strip()
        else:
            push()
            cur = line.strip()
        prev_blank = False
    push()
    items = []
    for d, raw in entries:
        raw = raw.strip()
        bold = re.match(r'\*\*(.+?)\*\*\s*:?\s*(.*)', raw, re.S)
        if bold:
            title, body = strip_md(bold.group(1)), strip_md(bold.group(2))
        else:
            plain = strip_md(raw)
            title, body = first_sentence(plain), plain
        if len(title) < 4 or len(body) + len(title) < 20:
            continue
        models = re.findall(r'`([a-z0-9][a-z0-9.\-]{2,60})`', raw)
        slug = d.strftime('%B-%-d-%Y').lower()
        items.append(_item(src, d, title, body, f'{base}#{slug}', models[:6]))
    return items


def md_month(src, text, today: dt.date):
    """xAI：'## October' 底下 '### 標題' + 段落。年份依月份往回推。"""
    items = []
    base = src.get('link') or src['url'].replace('.md', '')
    month = None
    year = today.year
    last_month = None
    title = None
    body = []

    def flush():
        if month and title:
            d = dt.date(year, month, 1)
            txt = strip_md(' '.join(body))
            models = re.findall(r'`([a-z0-9][a-z0-9.\-]{2,60})`', ' '.join(body))
            it = _item(src, d, strip_md(title), txt, base + '#' + re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-'),
                       models[:6])
            it['month_only'] = True
            items.append(it)

    for line in text.splitlines():
        m2 = re.match(r'^##\s+([A-Za-z]+)\s*(\d{4})?\s*$', line)
        m3 = re.match(r'^###\s+(.+?)\s*$', line)
        if m2 and m2.group(1).lower() in MONTHS:
            flush()
            title, body = None, []
            mm = MONTHS[m2.group(1).lower()]
            if m2.group(2):
                year = int(m2.group(2))
            elif last_month is None:
                year = today.year if mm <= today.month else today.year - 1
            elif mm > last_month:
                year -= 1
            month, last_month = mm, mm
        elif m3 and month:
            flush()
            title, body = m3.group(1), []
        elif month and title is not None:
            body.append(line)
    flush()
    return items


# ------------------------------------------------------------------ HTML 說明中心
def intercom(src, html):
    """Claude 說明中心：h3 是日期；只有粗體的段落是一條更新的標題，後面段落是內容。"""
    soup = BeautifulSoup(html, 'lxml')
    art = soup.find('article') or soup
    items = []
    for h in art.find_all(['h2', 'h3']):
        d = parse_date(h.get_text(' ', strip=True))
        if not d:
            continue
        anchor = h.get('id')
        url = src['url'] + (f'#{anchor}' if anchor else '')
        entries = []
        for el in h.find_all_next():
            if el.name in ('h2', 'h3'):
                break
            if el.name not in ('p', 'li'):
                continue
            if el.find_parent('li') is not None and el.name == 'p':
                continue
            txt = el.get_text(' ', strip=True)
            if not txt:
                continue
            bolds = ' '.join(b.get_text(' ', strip=True) for b in el.find_all(['b', 'strong']))
            if el.name == 'p' and bolds and bolds.strip() == txt:
                entries.append([txt, []])
            elif entries:
                entries[-1][1].append(txt)
            else:
                entries.append([first_sentence(txt), [txt]])
        for title, body in entries:
            items.append(_item(src, d, title, ' '.join(body), url))
    return items


def help_dated(src, html):
    """ChatGPT 說明中心：h1 是日期、h2 是一條更新的標題，後面是內容。"""
    soup = BeautifulSoup(html, 'lxml')
    art = soup.find('article') or soup
    items = []
    cur = None
    for h in art.find_all(['h1', 'h2']):
        txt = h.get_text(' ', strip=True)
        d = parse_date(txt)
        if d and h.name == 'h1':
            cur = d
            continue
        if not cur or h.name != 'h2':
            continue
        body = []
        for el in h.find_all_next():
            if el.name in ('h1', 'h2'):
                break
            if el.name in ('p', 'li') and not (el.name == 'p' and el.find_parent('li') is not None):
                t = el.get_text(' ', strip=True)
                if t:
                    body.append(t)
        anchor = h.get('id')
        items.append(_item(src, cur, txt, ' '.join(body), src['url'] + (f'#{anchor}' if anchor else '')))
    return items


def gemini_app(src, html):
    """Gemini App：h2 是日期（2026.10.13），h3 是功能標題。"""
    soup = BeautifulSoup(html, 'lxml')
    items = []
    cur = None
    for h in soup.find_all(['h2', 'h3']):
        txt = h.get_text(' ', strip=True)
        if h.name == 'h2':
            cur = parse_date(txt)
            continue
        if not cur:
            continue
        body = []
        for el in h.find_all_next():
            if el.name in ('h2', 'h3'):
                break
            if el.name in ('p', 'li'):
                t = el.get_text(' ', strip=True)
                if t and t not in body:
                    body.append(t)
        items.append(_item(src, cur, txt, ' '.join(body), src['url']))
    return items


def openai_changelog(src, html, today: dt.date):
    """OpenAI 開發者更新紀錄：月份標題＋每筆的日期徽章、類型徽章、模型徽章與內文。"""
    soup = BeautifulSoup(html, 'lxml')
    items = []
    for sec in soup.find_all(class_=re.compile('ChangelogSectionTitle')):
        my = _RX_MY.match(sec.get_text(' ', strip=True))
        year = int(my.group(2)) if my else today.year
        block = sec.parent
        for grid in block.find_all('div', class_=re.compile(r'\bgrid\b')):
            cells = grid.find_all('div', recursive=False)
            if len(cells) < 2:
                continue
            d = parse_date(cells[0].get_text(' ', strip=True), year)
            if not d:
                continue
            badges = [b.get_text(' ', strip=True) for b in cells[1].find_all(class_=re.compile('Badge'))]
            kind = badges[0] if badges else ''
            models = [b for b in badges[1:] if re.match(r'^[a-z0-9][a-z0-9.\-]+$', b) and not b.startswith('v1')]
            md = cells[1].find(class_=re.compile('MarkdownContent'))
            text = md.get_text(' ', strip=True) if md else cells[1].get_text(' ', strip=True)
            it = _item(src, d, first_sentence(text), text, src['url'], models[:6])
            it['kind_hint'] = kind.lower()
            items.append(it)
    return items


# ------------------------------------------------------------------ 新聞列表
def rss(src, raw: bytes):
    f = feedparser.parse(raw)
    items = []
    for e in f.entries[: src.get('max', 200)]:
        t = e.get('published_parsed') or e.get('updated_parsed')
        d = dt.date(t.tm_year, t.tm_mon, t.tm_mday) if t else None
        cats = [c.get('term') for c in e.get('tags', []) if c.get('term')]
        summ = strip_html(e.get('summary', ''))
        it = _item(src, d, e.get('title', ''), summ, e.get('link', src['url']))
        it['cats'] = cats[:5]
        items.append(it)
    return items


AN_CATS = {'announcements', 'features', 'partnerships', 'product', 'policy', 'security', 'safeguards', 'research',
           'societal-impacts', 'interpretability', 'alignment', 'economic-research', 'case-study', 'customer-stories',
           'event', 'events', 'education', 'company'}
AN_CAT_WORDS = ('Announcements', 'Policy', 'Product', 'Research', 'Societal Impacts', 'Interpretability', 'Alignment',
                'Economic Research', 'Case Study', 'Customer stories', 'Event', 'Features', 'Partnerships', 'Security',
                'Safeguards')


def _an_href(a):
    """文章連結 → '/news/<slug>'；分類頁（/news/announcements 這類）或其他連結 → None。"""
    href = (a.get('href') or '').split('?')[0].split('#')[0]
    if href.startswith('https://www.anthropic.com'):
        href = href[len('https://www.anthropic.com'):]
    if not href.startswith('/news/'):
        return None
    slug = href[len('/news/'):].strip('/')
    if not slug or '/' in slug or slug in AN_CATS or 'TopicLink' in ' '.join(a.get('class') or []):
        return None
    return '/news/' + slug


def anthropic_news(src, html):
    """Anthropic 公告列表。兩種版型都認：
    新版（2026-10-20 起）：每則一塊，裡面有分類連結、<time>、標題連結、摘要；
    舊版：整則包在一個 <a> 裡，日期、分類、標題都是它的文字。"""
    soup = BeautifulSoup(html, 'lxml')
    items, seen = [], set()
    for t in soup.find_all('time'):
        if t.find_parent('a') is not None:      # 舊版：日期在連結裡，交給下面處理
            continue
        d = parse_date(t.get('datetime', '') or t.get_text(' ', strip=True))
        if not d:
            continue
        box, href = t, None
        for _ in range(5):                       # 往外找到「剛好只有一篇文章連結」的那一塊
            box = box.parent
            if box is None:
                break
            hrefs = {h for h in (_an_href(a) for a in box.find_all('a', href=True)) if h}
            if len(hrefs) == 1:
                href = hrefs.pop()
                break
            if len(hrefs) > 1:
                break
        if not href or href in seen:
            continue
        head = box.find(['h1', 'h2', 'h3', 'h4'])
        texts = [a.get_text(' ', strip=True) for a in box.find_all('a', href=True) if _an_href(a) == href]
        title = head.get_text(' ', strip=True) if head else max(texts + [''], key=len)
        if not title:
            img = box.find('img', alt=True)
            title = img['alt'] if img else ''
        if len(title) < 6:
            continue
        cat = box.find('a', class_=re.compile('TopicLink'))
        body = ' '.join(p.get_text(' ', strip=True) for p in box.find_all('p')
                        if p.get_text(' ', strip=True) != title and not p.find('a', class_=re.compile('TopicLink')))
        seen.add(href)
        it = _item(src, d, title, body, 'https://www.anthropic.com' + href)
        it['cats'] = [cat.get_text(' ', strip=True)] if cat else []
        items.append(it)
    for a in soup.find_all('a', href=True):
        href = _an_href(a)
        if not href or href in seen:
            continue
        parts = [p for p in a.get_text('|', strip=True).split('|') if p.strip()]
        d, cat, rest = None, '', []
        for p in parts:
            pd = parse_date(p)
            if pd and not d:
                d = pd
            elif p in AN_CAT_WORDS:
                cat = p
            else:
                rest.append(p)
        if not d or not rest:
            continue
        seen.add(href)
        title = max(rest[:2], key=len) if len(rest) > 1 and len(rest[0]) < 25 else rest[0]
        body = ' '.join(r for r in rest if r != title)
        it = _item(src, d, title, body, 'https://www.anthropic.com' + href)
        it['cats'] = [cat] if cat else []
        items.append(it)
    items.sort(key=lambda x: x['d'] or '', reverse=True)
    return items


def xai_news(src, html):
    soup = BeautifulSoup(html, 'lxml')
    items, seen = [], set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/news/' not in href or href.rstrip('/').endswith('/news'):
            continue
        url = urllib.parse.urljoin('https://x.ai', href)
        if url in seen:
            continue
        parts = [p.strip() for p in a.get_text('|', strip=True).split('|')]
        parts = [p for p in parts if p and p not in ('·', 'Read More', 'Product', 'Company', 'Research', 'News')]
        d = None
        rest = []
        for p in parts:
            pd = parse_date(p)
            if pd and not d:
                d = pd
            else:
                rest.append(p)
        if not rest:
            continue
        seen.add(url)
        it = _item(src, d, rest[0], ' '.join(rest[1:]), url)
        items.append(it)
    return items


# ------------------------------------------------------------------ GitHub releases / Claude Code
HL_WORDS = re.compile(
    r'\b(Pro|Max|Plus|usage|limit|limits|quota|plan|subscription|Windows|desktop|Desktop|Cowork|PowerShell|'
    r'model|Opus|Sonnet|Haiku|Fable|GPT|Gemini|cost|token|faster|speed|memory|context|image|video|voice|'
    r'CUDA|RTX|Blackwell|GPU|VRAM|offload|Flux|FLUX|Wan|LTX|Qwen|Gemma|Llama|DeepSeek|new model|support for)\b')


def _bullets(md: str):
    out = []
    for line in (md or '').splitlines():
        m = re.match(r'^\s*[*\-]\s+(.*)', line)
        if m:
            t = strip_md(re.sub(r'\s+by @[\w\-]+(\s+in\s+https?://\S+)?', '', m.group(1)))
            t = re.sub(r'\s*\(#?\d{3,6}\)\s*$', '', re.sub(r'\s+in\s+https?://\S+$', '', t)).strip()
            if len(t) > 8:
                out.append(t)
    return out


def pick_highlights(lines, n=3):
    added = [l for l in lines if re.match(r'^(Added|New|Introduc|Support|Improved|Made|Changed|Updated)', l)]
    fixed = [l for l in lines if re.match(r'^Fix', l)]
    ranked = sorted(lines, key=lambda l: (-(bool(HL_WORDS.search(l)) * 2 + (l in added)), lines.index(l)))
    hl = [l for l in ranked if l not in fixed][:n] or ranked[:n]
    return hl, len(added), len(fixed)


def gh_releases(src, data, include_pre=False):
    items = []
    for r in data:
        if r.get('draft') or (r.get('prerelease') and not include_pre):
            continue
        tag = r.get('tag_name') or ''
        if re.search(src.get('skip_tag', r'(nightly|preview|alpha|beta|rc\d*)'), tag, re.I):
            continue
        t = r.get('published_at') or r.get('created_at')
        d = dt.date.fromisoformat(t[:10]) if t else None
        lines = _bullets(r.get('body') or '')
        hl, n_add, n_fix = pick_highlights(lines)
        ver = re.sub(r'^(rust-)?v', '', tag)
        it = _item(src, d, f"{src['product']} {ver}", ' '.join(hl) or strip_md(r.get('body') or '')[:400],
                   r.get('html_url') or src.get('home'))
        it.update(ver=ver, hl=hl, n_add=n_add, n_fix=n_fix, n_lines=len(lines), tool=True)
        items.append(it)
    return items


def claude_code(src, changelog_md: str, npm: dict):
    times = npm.get('time') or {}
    items = []
    for m in re.finditer(r'^##\s+(\d+\.\d+\.\d+)\s*$(.*?)(?=^##\s+\d|\Z)', changelog_md, re.M | re.S):
        ver, body = m.group(1), m.group(2)
        t = times.get(ver)
        if not t:
            continue
        lines = _bullets(body)
        hl, n_add, n_fix = pick_highlights(lines)
        it = _item(src, dt.date.fromisoformat(t[:10]), f'Claude Code {ver}', ' '.join(hl),
                   f'https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#{ver.replace(".", "")}')
        it.update(ver=ver, hl=hl, n_add=n_add, n_fix=n_fix, n_lines=len(lines), tool=True)
        items.append(it)
        if len(items) >= 60:
            break
    return items


def lmstudio(src, html):
    """LM Studio 更新紀錄頁：抓版本標題（LM Studio 0.x.y／Bionic x.y.z）與底下條列。"""
    soup = BeautifulSoup(html, 'lxml')
    items = []
    for h in soup.find_all(['h1', 'h2', 'h3']):
        txt = h.get_text(' ', strip=True)
        m = re.match(r'^(LM Studio|Bionic)\s+v?(\d+\.\d+(?:\.\d+)*)', txt)
        if not m:
            continue
        lines, d = [], None
        for el in h.find_all_next():
            if el.name in ('h1', 'h2', 'h3') and el is not h:
                break
            if el.name == 'time' and not d:
                d = parse_date(el.get('datetime', '') or el.get_text(' ', strip=True))
            if el.name == 'li':
                t = el.get_text(' ', strip=True)
                if t:
                    lines.append(t)
            if not d and el.name in ('p', 'span', 'div') and len(el.get_text(strip=True)) < 40:
                d = parse_date(el.get_text(' ', strip=True))
        hl, n_add, n_fix = pick_highlights(lines)
        it = _item(src, d, txt, ' '.join(hl), src['url'])
        it.update(ver=m.group(2), app=m.group(1), hl=hl, n_add=n_add, n_fix=n_fix, n_lines=len(lines), tool=True)
        items.append(it)
    return items


def nvidia(src, text):
    try:
        data = json.loads(text)
    except ValueError:
        return []
    items = []
    for x in data.get('IDS', [])[:3]:
        info = x.get('downloadInfo') or {}
        ver = info.get('Version')
        if not ver:
            continue
        name = urllib.parse.unquote(info.get('Name') or 'GeForce 驅動程式')
        try:
            d = dt.date(*map(int, (info.get('ReleaseDateTime') or '').split('-')))
        except (TypeError, ValueError):
            d = None
        it = _item(src, d, f'{name} {ver}', urllib.parse.unquote(info.get('ShortDescription') or ''),
                   info.get('DetailsURL') or src['url'])
        it.update(ver=ver, tool=True, zh_native=True)
        items.append(it)
    return items
