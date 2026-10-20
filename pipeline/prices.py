"""API 價格表：直接讀四家官方的價格頁與停用表，OpenRouter 只拿來交叉核對。

輸出每個模型的現價、快取價、批次價、未來調價、停用日期；和上一輪比對，產生「價格異動」「新模型上架」事件。
"""
import datetime as dt
import re

from bs4 import BeautifulSoup

from .feeds import parse_date
from .util import iso, strip_html

MONEY = re.compile(r'\$\s?([\d,]*\.?\d+)')


def money(s):
    if s is None:
        return None
    m = MONEY.search(str(s))
    return float(m.group(1).replace(',', '')) if m else None


def md_tables(text):
    """把 markdown 文字裡所有表格切出來：[(表格前最近的標題, [列, ...]), ...]，列是儲存格字串陣列。"""
    out, cur, head = [], None, ''
    for line in text.splitlines():
        if line.startswith('#'):
            head = line.lstrip('#').strip()
        if line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if all(re.match(r'^:?-{2,}:?$', c) or not c for c in cells):
                continue
            if cur is None:
                cur = (head, [])
                out.append(cur)
            cur[1].append(cells)
        else:
            cur = None
    return out


def _slug(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def _rec(v, mid, name, **kw):
    r = {'v': v, 'id': mid, 'name': name}
    r.update({k: val for k, val in kw.items() if val is not None})
    return r


# ------------------------------------------------------------------ Claude
def claude(pricing_md, deprec_md, models_md):
    status = {}
    replace = {}
    for head, rows in md_tables(deprec_md):
        if rows and rows[0][0].lower().startswith('api model name'):
            for r in rows[1:]:
                if len(r) >= 4:
                    status[r[0].strip('` ')] = {'st': r[1].lower(), 'dep': r[2], 'retire': r[3]}
        elif rows and 'recommended replacement' in ' '.join(rows[0]).lower():
            for r in rows[1:]:
                if len(r) >= 3:
                    replace.setdefault(r[1].strip('` '), r[2].strip('` '))
    info = {}
    for head, rows in md_tables(models_md):
        if not rows or not rows[0][0].lower().startswith('feature'):
            continue
        names = [strip_html(re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', c)) for c in rows[0][1:]]
        for r in rows[1:]:
            key = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', r[0]).lower()
            for i, n in enumerate(names):
                if i + 1 < len(r):
                    info.setdefault(n, {})[key] = strip_html(re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', r[i + 1])).strip('` ')
    batch = {}
    models = []
    for head, rows in md_tables(pricing_md):
        hdr = [c.lower() for c in rows[0]] if rows else []
        if hdr and hdr[0] == 'model' and any('batch input' in h for h in hdr):
            for r in rows[1:]:
                batch[_slug(re.sub(r'\(.*?\)', '', strip_html(r[0])))] = (money(r[1]), money(r[2]))
    for head, rows in md_tables(pricing_md):
        hdr = [c.lower() for c in rows[0]] if rows else []
        if not (hdr and hdr[0] == 'model' and any('base input' in h for h in hdr)):
            continue
        for r in rows[1:]:
            raw = strip_html(re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', r[0]))
            note = ''
            m = re.search(r'\((.*?)\)', raw)
            if m:
                note = m.group(1)
            name = re.sub(r'\s*\(.*?\)\s*', ' ', raw).strip()
            if 'over' in note and 'tokens' in note:
                continue      # 長上下文那一列併到同模型的 long
            mid = None
            for k in status:
                if _slug(k) == _slug(name) or re.sub(r'\d{8}$', '', _slug(k)) == _slug(name):
                    mid = k
                    break
            mid = mid or re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
            st = status.get(mid, {})
            inf = info.get(name, {})
            b = batch.get(_slug(name), (None, None))
            rec = _rec('claude', mid, name, inp=money(r[1]), cw=money(r[2]), cw1h=money(r[3]), cr=money(r[4]),
                       out=money(r[5]), bin=b[0], bout=b[1], note=note or None,
                       status=st.get('st') or ('retired' if 'retired' in note else 'active'),
                       retire=st.get('retire'), replace=replace.get(mid), desc=inf.get('description'),
                       ctx=inf.get('context window'),
                       maxout=inf.get('max output'))
            if 'up to' in note:
                rec['note'] = '提示詞 10 萬 token 以內'
                long_row = next((x for x in rows[1:] if name in x[0] and 'over' in x[0]), None)
                if long_row:
                    rec['long'] = {'inp': money(long_row[1]), 'out': money(long_row[5]), 'over': '10 萬 token'}
            if 'limited availability' in note:
                rec['note'] = '限量開放'
            elif 'retired' in note:
                rec['note'] = None
            models.append(rec)
    return models, status


# ------------------------------------------------------------------ Gemini
_FUT = re.compile(r'\$([\d.]+)\s+through\s+([A-Za-z]+ \d{1,2}, \d{4})\.\s*\$([\d.]+)\s+starting\s+([A-Za-z]+ \d{1,2}, \d{4})')


def _gem_price(cell):
    """'$2.00 through November 30, 2026. $4.00 starting December 1, 2026.' → (2.0, {'p':4.0,'from':date})"""
    if cell is None:
        return None, None
    m = _FUT.search(cell)
    if m:
        d = parse_date(m.group(4))
        return float(m.group(1)), {'p': float(m.group(3)), 'from': d.isoformat() if d else None}
    nums = MONEY.findall(cell)
    if not nums:
        return None, None
    return float(nums[0].replace(',', '')), None


def gemini(pricing_md, deprec_md):
    status = {}
    for head, rows in md_tables(deprec_md):
        if rows and 'model' in rows[0][0].lower() and len(rows[0]) >= 3:
            for r in rows[1:]:
                mid = r[0].strip('`* ')
                if not re.match(r'^[a-z0-9.\-]+$', mid):
                    continue
                shut = r[2] if len(r) > 2 else ''
                rep = (r[3] if len(r) > 3 else '').split('(')[0].strip('` ')
                status[mid] = {'shut': shut, 'replace': rep or None,
                               'routed': 'automatically routes' in (r[3] if len(r) > 3 else '')}
    models = []
    sections = re.split(r'^## ', pricing_md, flags=re.M)
    for sec in sections[1:]:
        title = sec.splitlines()[0].strip()
        title = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', title).replace('🍌', '').strip()
        ids = re.findall(r'`(gemini-[a-z0-9.\-]+|veo-[a-z0-9.\-]+|lyria-[a-z0-9.\-]+)`', sec[:600])
        if not ids or re.search(r'tts|embedding|robotics|live|transcribe|audio|veo|lyria', ids[0]):
            continue
        kind = 'image' if re.search(r'image|banana', ids[0] + title.lower()) else 'text'
        std = re.split(r'^### ', sec, flags=re.M)
        block = next((b for b in std if b.lower().startswith('standard')), None) or (std[0] if std else '')
        rows = {}
        for _, tr in md_tables(block):
            for r in tr:
                if len(r) >= 3:
                    rows[r[0].lower()] = r
        ip = next((v for k, v in rows.items() if k.startswith('input price')), None)
        op = next((v for k, v in rows.items() if k.startswith('output price')), None)
        cp = next((v for k, v in rows.items() if k.startswith('context caching')), None)
        if not ip or not op:
            continue
        inp, fin = _gem_price(ip[2])
        out, fout = _gem_price(op[2])
        cr, _ = _gem_price(cp[2] if cp else None)
        free = 'free of charge' in (ip[1] or '').lower()
        if inp is None or out is None:
            continue
        mid = ids[0]
        st = status.get(mid, {})
        fut = None
        if fin or fout:
            fut = {'inp': (fin or {}).get('p'), 'out': (fout or {}).get('p'), 'from': (fin or fout or {}).get('from')}
        note = None
        if 'not available on the free tier' in sec[:1500].lower():
            note = '免費額度不能用'
        elif free:
            note = '有免費額度'
        long_note = None
        if re.search(r'prompts?\s*(?:<=|≤|>|over)\s*200', ip[2], re.I):
            long_note = '超過 20 萬 token 較貴'
        status_word = 'active'
        if 'preview' in mid:
            status_word = 'preview'
        if st.get('replace') and st.get('routed'):
            status_word = 'deprecated'
        if kind == 'image':
            continue          # 生圖模型改用「每張圖」計價，不放進 token 價格表
        models.append(_rec('gemini', mid, title, inp=inp, out=out, cr=cr, fut=fut, note=note, long=long_note,
                           status=status_word, retire=st.get('shut') if st.get('shut') not in (None, '', 'N/A') else None,
                           replace=st.get('replace')))
    return models, status


# ------------------------------------------------------------------ xAI
def xai(pricing_md):
    models = {}
    for head, rows in md_tables(pricing_md):
        if not rows or rows[0][0].lower() != 'model' or not any('input' in c.lower() for c in rows[0]):
            continue
        for r in rows[1:]:
            if len(r) < 5:
                continue
            raw = r[0]
            mid = raw.split('(')[0].strip()
            longrow = '≥' in raw or '>=' in raw
            if longrow:
                if mid in models:
                    models[mid]['long'] = {'inp': money(r[2]), 'out': money(r[4]), 'over': '20 萬 token'}
                continue
            name = 'Grok ' + ' '.join(w if re.match(r'^[\d.]+$', w) else w.capitalize()
                                      for w in mid.replace('grok-', '').split('-'))
            models[mid] = _rec('grok', mid, name, inp=money(r[2]), cr=money(r[3]), out=money(r[4]),
                               ctx=r[1], status='active')
    return list(models.values())


# ------------------------------------------------------------------ OpenAI
def openai(pricing_html, deprec_html):
    soup = BeautifulSoup(pricing_html, 'lxml')
    models = []
    tables = soup.find_all('table')
    std = None
    for t in tables:
        heads = [c.get_text(' ', strip=True).lower() for c in t.find_all('th')]
        if 'model' in heads and 'input' in heads and 'output' in heads:
            std = t
            break
    if std is not None:
        for tr in std.find_all('tr'):
            cells = [c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'])]
            if len(cells) < 5 or not re.match(r'^[a-z0-9][a-z0-9.\-]+$', cells[0]):
                continue
            mid = cells[0]
            name = re.sub(r'^gpt-', 'GPT-', mid)
            name = ' '.join(p.capitalize() if i else p for i, p in enumerate(re.split(r'(?<=\d)-(?=[a-z])', name)))
            long = None
            if len(cells) >= 9 and money(cells[5]):
                long = {'inp': money(cells[5]), 'out': money(cells[8]), 'over': '長上下文'}
            models.append(_rec('chatgpt', mid, name, inp=money(cells[1]), cr=money(cells[2]), cw=money(cells[3]),
                               out=money(cells[4]), long=long, status='active'))
    retire = {}
    dsoup = BeautifulSoup(deprec_html or '', 'lxml')
    for t in dsoup.find_all('table'):
        heads = [c.get_text(' ', strip=True).lower() for c in t.find_all('th')]
        if not heads or 'shutdown date' not in heads[0]:
            continue
        for tr in t.find_all('tr')[1:]:
            cells = [c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'])]
            if len(cells) < 2:
                continue
            for mid in re.findall(r'\b(gpt-[a-z0-9.\-]+|o\d[a-z0-9.\-]*|codex-[a-z0-9.\-]+)\b', cells[1]):
                retire.setdefault(mid, {'shut': cells[0], 'replace': cells[2] if len(cells) > 2 else None})
    for m in models:
        if m['id'] in retire:
            m['status'] = 'deprecated'
            m['retire'] = retire[m['id']]['shut']
            m['replace'] = retire[m['id']]['replace']
    return models, retire


# ------------------------------------------------------------------ OpenRouter 交叉核對
OR_PREFIX = {'claude': 'anthropic/', 'chatgpt': 'openai/', 'gemini': 'google/', 'grok': 'x-ai/'}


def cross_check(models, openrouter):
    idx = {}
    for m in openrouter or []:
        mid = m.get('id', '')
        if ':' in mid:
            continue
        idx[_slug(mid.split('/', 1)[-1])] = m
    for m in models:
        o = idx.get(_slug(m['id']))
        if not o:
            continue
        p = o.get('pricing') or {}
        try:
            oi = round(float(p.get('prompt') or 0) * 1e6, 4)
            oo = round(float(p.get('completion') or 0) * 1e6, 4)
        except ValueError:
            continue
        m['or'] = {'inp': oi, 'out': oo}
        if m.get('inp') is not None and m.get('out') is not None:
            m['agree'] = abs(oi - m['inp']) < 0.011 and abs(oo - m['out']) < 0.011
        if o.get('context_length') and not m.get('ctx'):
            m['ctx'] = f"{o['context_length'] // 1000}K" if o['context_length'] < 1_000_000 else f"{o['context_length'] / 1e6:g}M"
        if o.get('created') and not m.get('rel'):
            m['rel'] = dt.datetime.fromtimestamp(o['created'], dt.timezone.utc).date().isoformat()
    return models


# ------------------------------------------------------------------ 和上一輪比對
def diff(models, prev: dict, t0):
    """prev: {vendor/id: {'inp','out','seen'}}。回傳 (新的 prev, 事件)。第一次看到整批時不產生事件。"""
    events = []
    first_run = not prev
    now = iso(t0)
    nxt = {}
    for m in models:
        key = f"{m['v']}/{m['id']}"
        old = prev.get(key)
        rec = {'inp': m.get('inp'), 'out': m.get('out'), 'seen': (old or {}).get('seen') or now,
               'hist': (old or {}).get('hist', [])}
        if old is None and not first_run and m.get('status') not in ('retired',):
            events.append({'type': 'new_model', 'v': m['v'], 'id': m['id'], 'name': m['name'],
                           'inp': m.get('inp'), 'out': m.get('out'), 'at': now})
        elif old is not None:
            for f in ('inp', 'out'):
                a, b = old.get(f), m.get(f)
                if a is not None and b is not None and abs(a - b) > 1e-9:
                    events.append({'type': 'price', 'v': m['v'], 'id': m['id'], 'name': m['name'], 'field': f,
                                   'from': a, 'to': b, 'at': now})
                    rec['hist'] = (rec['hist'] + [{'at': now, 'f': f, 'from': a, 'to': b}])[-12:]
        m['seen'] = rec['seen']
        if rec['hist']:
            m['chg'] = rec['hist'][-1]
        nxt[key] = rec
    for key, old in prev.items():          # 這輪沒抓到的模型先留著（可能只是頁面暫時抓不到）
        nxt.setdefault(key, old)
    return nxt, events


def upcoming(models, today: dt.date, horizon_days=120):
    """未來會發生的事：漲價／降價生效日、停用日。"""
    out = []
    for m in models:
        f = m.get('fut')
        if f and f.get('from'):
            d = dt.date.fromisoformat(f['from'])
            if today <= d <= today + dt.timedelta(days=horizon_days):
                up = (f.get('inp') or 0) > (m.get('inp') or 0) or (f.get('out') or 0) > (m.get('out') or 0)
                out.append({'type': 'price_future', 'v': m['v'], 'id': m['id'], 'name': m['name'], 'd': f['from'],
                            'up': up, 'inp': [m.get('inp'), f.get('inp')], 'out': [m.get('out'), f.get('out')]})
        r = m.get('retire')
        if r and m.get('status') in ('deprecated', 'legacy', 'active', 'preview'):
            if str(r).lower().startswith('not sooner'):
                continue
            d = parse_date(str(r))
            if d and today <= d <= today + dt.timedelta(days=horizon_days):
                out.append({'type': 'retire', 'v': m['v'], 'id': m['id'], 'name': m['name'], 'd': d.isoformat(),
                            'replace': m.get('replace')})
    return sorted(out, key=lambda x: x['d'])


# ------------------------------------------------------------------ 主力型號與等級
FAMILY = {
    'claude': (r'^claude-(fable|mythos|opus|sonnet|haiku)-(\d+)(?:-(\d))?(?:-\d{8})?$', None),
    'gemini': (r'^gemini-(\d+)(?:\.(\d+))?-(argon|pro|flash-lite|flash)(?:-preview)?(?:-[\d-]+)?$', None),
    'chatgpt': (r'^gpt-(\d+)(?:\.(\d+))?-([a-z]+)$', None),
    'grok': (r'^grok-(?:(build)-)?(\d+)\.(\d+)$', None),
}


def family_version(v, mid):
    """回傳 (家族, 版本數字)；對不上規則就回傳 (None, None)。"""
    rx = FAMILY.get(v, (None,))[0]
    m = re.match(rx, mid) if rx else None
    if not m:
        return None, None
    g = m.groups()
    if v == 'claude':
        return g[0], float(f'{g[1]}.{g[2] or 0}')
    if v == 'gemini':
        return g[2], float(f'{g[0]}.{g[1] or 0}')
    if v == 'chatgpt':
        return g[2], float(f'{g[0]}.{g[1] or 0}')
    if v == 'grok':
        return (g[0] or 'grok'), float(f'{g[1]}.{g[2]}')
    return None, None


def mark_main(models, tiers: dict):
    """每家每個家族只標最新的一個為「主力型號」；預覽版若已有更新的正式版就不標。等級名稱由 config 決定。"""
    best = {}
    ga_top = {}
    for m in models:
        if m.get('status') in ('retired',):
            continue
        fam, ver = family_version(m['v'], m['id'])
        if fam is None:
            continue
        m['fam'], m['ver'] = fam, ver
        if m.get('status') != 'preview':
            ga_top[m['v']] = max(ga_top.get(m['v'], 0), ver)
        key = (m['v'], fam)
        cur = best.get(key)
        if cur is None or ver > cur['ver'] or (ver == cur['ver'] and cur.get('status') == 'preview'):
            best[key] = m
    for (v, fam), m in best.items():
        if m.get('status') == 'preview' and ga_top.get(v, 0) > m['ver']:
            continue
        if m.get('status') == 'deprecated':
            continue
        m['main'] = True
        m['tier'] = (tiers.get(v) or {}).get(fam)
    return models
