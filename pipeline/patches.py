"""改版公告：分類（加強／削弱／新增／移除／調整／修正）、貼標籤、算「跟你有關」分數、合併同一件事。

全部是 config/rules.json 的固定規則，比對官方英文原文；分數一定附理由（why）。
"""
import datetime as dt
import math
import re

from .util import sid

FX_ZH = {'gone': '移除', 'nerf': '削弱', 'buff': '加強', 'new': '新增', 'fix': '修正', 'tweak': '調整'}
# 公告裡提到的是「方案家族」（例如 Max、Pro），config/plans.json 的方案 id 再對應到家族
TIER_ORDER = {
    'claude': ['free', 'pro', 'max'],
    'chatgpt': ['free', 'go', 'plus', 'pro'],
    'gemini': ['free', 'plus', 'pro', 'ultra'],
    'grok': ['free', 'plus', 'premium', 'super', 'ultra'],
}
TIER_FAMILY = {'max5': 'max', 'max20': 'max', 'pro100': 'pro', 'pro200': 'pro', 'pro500': 'pro', 'ultra20': 'ultra'}
TIER_ZH = {'free': '免費版', 'pro': 'Pro', 'max5': 'Max', 'max20': 'Max', 'go': 'Go', 'plus': 'Plus', 'ultra': 'Ultra',
           'ultra20': 'Ultra', 'pro100': 'Pro', 'pro200': 'Pro', 'pro500': 'Pro', 'premium': 'X Premium', 'super': 'X Super'}
VENDOR_ZH = {'claude': 'Claude', 'chatgpt': 'ChatGPT', 'gemini': 'Gemini', 'grok': 'Grok', 'local': '本機工具'}
STOP = set('a an the and or of to in on for with is are be now new our your you we it its this that from by at as '
           'available introducing announcing update updates model models'.split())


class Rules:
    def __init__(self, cfg: dict, profile: dict):
        self.cfg = cfg
        self.w = cfg['weights']
        self.tiers = profile.get('tiers') or {}
        self.fx = {k: [re.compile(p, re.I) for p in v] for k, v in cfg['fx'].items()}
        self.tags = {k: [re.compile(p, re.I) for p in v] for k, v in cfg['tags'].items()}
        self.plan = {v: {t: [re.compile(p, re.I) for p in ps] for t, ps in m.items()}
                     for v, m in cfg['plan_words'].items()}
        self.newsroom = set(cfg.get('cats_newsroom') or [])
        self.news_sources = set(cfg.get('news_sources') or [])
        self.product = re.compile(cfg.get('product_words') or r'^$', re.I)

    def classify(self, it):
        text = f"{it['t']} {it.get('b') or ''}"
        head = it['t']
        fx = None
        if it.get('fx'):
            fx = it['fx']
        elif it.get('tool'):
            fx = 'new' if it.get('n_add') else ('fix' if it.get('n_fix') else 'tweak')
            if any(p.search(' '.join(it.get('hl') or [])) for p in self.fx['gone']):
                fx = 'tweak'
        else:
            for k in self.cfg['fx_order']:
                pats = self.fx.get(k) or []
                # 標題命中優先；內文命中只算「移除／削弱／加強／新增」這類明確字眼
                if any(p.search(head) for p in pats) or (k != 'fix' and any(p.search(text) for p in pats)):
                    fx = k
                    break
            if (it.get('kind_hint') or '') == 'fix':
                fx = 'fix'
        fx = fx or 'tweak'
        title_only = set(self.cfg.get('tag_title_only') or [])
        tags = [k for k, pats in self.tags.items() if any(p.search(head if k in title_only else text) for p in pats)]
        if fx == 'gone' and '新模型' in tags:
            tags.remove('新模型')
        if set(it.get('cats') or []) & self.newsroom and '新聞稿' not in tags and fx not in ('gone', 'nerf'):
            tags.append('新聞稿')
        if it['src'] in self.news_sources and not self.product.search(head) and '新聞稿' not in tags:
            tags.append('新聞稿')       # 公司新聞標題沒提到任何產品，多半是企業、政策、活動消息
        if it.get('tool') and '程式' not in tags and it['v'] != 'local':
            tags.append('程式')
        if it['v'] == 'local':
            tags = [t for t in tags if t not in ('企業', '新聞稿')]
            if '本機' not in tags:
                tags.insert(0, '本機')
        for t in it.get('force_tags') or []:
            if t not in tags:
                tags.append(t)
        return fx, tags

    def plan_hit(self, v, text):
        mine = self.tiers.get(v)
        if v not in TIER_ORDER or not mine:
            return None
        mine = TIER_FAMILY.get(mine, mine)
        hits = [t for t, pats in self.plan.get(v, {}).items() if any(p.search(text) for p in pats)]
        if not hits:
            return None
        order = TIER_ORDER[v]
        if mine in hits:
            return 'mine'
        if mine in order and all(h in order and order.index(h) > order.index(mine) for h in hits):
            return 'higher'
        return None

    def score(self, it, fx, tags, today: dt.date):
        w = self.w
        why = []
        s = w['vendor'].get(it['v'], 10)
        if it['v'] == 'claude':
            why.append('Claude 是你的主力')
        elif it['v'] == 'chatgpt' and self.tiers.get('chatgpt') not in (None, 'free'):
            why.append(f"你有 ChatGPT {TIER_ZH.get(self.tiers['chatgpt'], '')}")
        s += w['source'].get(it['src'], 0)
        s += w['fx'].get(fx, 0)
        tag_pts = []
        for t in tags:
            pts = w['tags'].get(t, 0)
            s += pts
            if pts >= 6:
                tag_pts.append((pts, t))
        for pts, t in sorted(tag_pts, reverse=True)[:2]:
            why.append({'額度': '跟額度有關', '價格': '跟價格有關', '新模型': '新模型', '程式': '跟寫程式有關',
                        '生影片': '跟生影片有關', 'Windows': '跟 Windows 有關', '台灣': '提到台灣'}.get(t, t))
        ph = self.plan_hit(it['v'], f"{it['t']} {it.get('b') or ''}")
        if ph == 'mine':
            s += w['my_plan']
            why.append(f"適用你的 {TIER_ZH.get(self.tiers.get(it['v']), '')} 方案")
        elif ph == 'higher':
            s += w['other_plan_only']
            why.append('要更高的方案才有')
        if '企業' in tags:
            why.append('偏企業版')
        if '新聞稿' in tags:
            why = ['公司新聞稿，跟使用沒直接關係']
            s = min(s, 5)
        s = max(0, min(100, s))
        age = (today - dt.date.fromisoformat(it['d'])).days if it.get('d') else 30
        rk = s * math.pow(0.5, max(0, age) / w['half_life_days'])
        return round(s), round(rk, 2), why[:3]


def _words(s):
    return {x for x in re.findall(r'[a-z0-9][a-z0-9.\-]+', (s or '').lower()) if x not in STOP and len(x) > 2}


SRC_RANK = {'claude_apps': 0, 'chatgpt_notes': 0, 'gemini_app': 0, 'claude_api': 1, 'openai_api': 1, 'gemini_api': 1,
            'xai_api': 1, 'anthropic_news': 2, 'openai_news': 2, 'google_blog': 2, 'xai_news': 2}


MODEL_KEY = re.compile(r'\b(claude (?:fable|mythos|opus|sonnet|haiku) \d+(?:\.\d+)?|gpt-\d+(?:\.\d+)?(?: (?:astra|sol|luna|pro))?|'
                       r'gemini \d+(?:\.\d+)? (?:argon|pro|flash-lite|flash)|nano banana \d+(?:\.\d+)?|veo \d+(?:\.\d+)?|'
                       r'grok \d+(?:\.\d+)?|grok voice \d+(?:\.\d+)?|sora \d+)\b', re.I)


def model_keys(it):
    return {m.lower().replace('-', ' ') for m in MODEL_KEY.findall(it['t'])}


def merge(items):
    """同一家、三天內、標題用字重疊一半以上 → 視為同一件事，保留最官方的那則，其餘列在 also。"""
    items = sorted(items, key=lambda x: (x.get('d') or '', -SRC_RANK.get(x['src'], 3)), reverse=True)
    kept = []
    for it in items:
        if it.get('tool') or it['src'] == 'prices':
            kept.append(it)
            continue
        ws = _words(it['t'])
        hit = None
        for k in kept:
            if k['v'] != it['v'] or k.get('tool') or k['src'] == it['src'] or k['src'] == 'prices':
                continue
            if not k.get('d') or not it.get('d'):
                continue
            if abs((dt.date.fromisoformat(k['d']) - dt.date.fromisoformat(it['d'])).days) > 3:
                continue
            kw = _words(k['t'])
            same_model = (model_keys(k) & model_keys(it)) and k.get('fx') in ('new', 'gone') and it.get('fx') in ('new', 'gone')
            if same_model or (ws and kw and len(ws & kw) / max(1, min(len(ws), len(kw))) >= 0.6):
                hit = k
                break
        if hit is None:
            kept.append(it)
            continue
        a, b = (hit, it) if SRC_RANK.get(hit['src'], 3) <= SRC_RANK.get(it['src'], 3) else (it, hit)
        if a is it:
            kept[kept.index(hit)] = it
        a.setdefault('also', []).append({'src': b['src'], 'p': b['p'], 'url': b['url'], 't': b['t']})
        a['also'].extend(b.get('also') or [])
    return kept


def price_items(events, today: dt.date, page_urls: dict):
    """價格表的變動 → 改版項目（直接寫中文，不用翻譯）。"""
    out = []
    for e in events:
        d = (e.get('at') or today.isoformat())[:10]
        if e['type'] == 'price':
            f = '輸入' if e['field'] == 'inp' else '輸出'
            up = e['to'] > e['from']
            t = f"{e['name']} API {f}價格 ${e['from']:g} → ${e['to']:g}"
            body = f"每百萬 token 的{f}價格從 ${e['from']:g} {'調漲' if up else '調降'}到 ${e['to']:g}（官方價格表）。"
            fx = 'nerf' if up else 'buff'
        elif e['type'] == 'new_model':
            t = f"{e['name']} 上架 API"
            body = f"官方價格表出現新模型 {e['name']}：每百萬 token 輸入 ${e['inp']:g}、輸出 ${e['out']:g}。" \
                if e.get('inp') is not None and e.get('out') is not None else f"官方價格表出現新模型 {e['name']}。"
            fx = 'new'
        else:
            continue
        out.append({'id': sid(f"prices|{e['v']}|{e['id']}|{e['type']}|{d}|{t}"), 'src': 'prices', 'v': e['v'],
                    'p': 'API 價格表', 'd': d, 't': t, 'b': body, 'tz': t, 'sz': body, 'zh_native': True,
                    'url': page_urls.get(e['v']), 'fx': fx, 'force_tags': ['價格'] + (['新模型'] if fx == 'new' else []),
                    'models': [e['id']]})
    return out


def weekly_tools(items, sources: set, today: dt.date):
    """每天出一版的工具（Claude Code、Codex、Ollama…）一週併成一則，重點挑最相關的三條。"""
    keep, groups = [], {}
    for it in items:
        if it['src'] in sources and it.get('tool') and it.get('d'):
            d = dt.date.fromisoformat(it['d'])
            mon = d - dt.timedelta(days=d.weekday())
            groups.setdefault((it['src'], mon), []).append(it)
        else:
            keep.append(it)
    from .feeds import HL_WORDS
    for (src, mon), its in groups.items():
        its.sort(key=lambda x: x['d'], reverse=True)
        if len(its) == 1:
            keep.append(its[0])
            continue
        lines = []
        for x in its:
            for h in x.get('hl') or []:
                if h not in lines:
                    lines.append(h)
        ranked = sorted(lines, key=lambda l: (-(bool(HL_WORDS.search(l)) * 2 + bool(re.match(r'^(Added|New|Introduc|Support)', l))), lines.index(l)))
        new, old = its[0], its[-1]
        name = new['p']
        this_week = mon == today - dt.timedelta(days=today.weekday())
        when = '本週' if this_week else f'{mon.month}/{mon.day} 那週'
        g = dict(new)
        g.update(t=f"{name} {when}更新 {len(its)} 版（{old.get('ver')}–{new.get('ver')}）", hl=ranked[:3], b=' '.join(ranked[:3]),
                 n_add=sum(x.get('n_add') or 0 for x in its), n_fix=sum(x.get('n_fix') or 0 for x in its),
                 vers=[x.get('ver') for x in its], id=sid(f"week|{src}|{mon.isoformat()}|{new.get('ver')}"))
        keep.append(g)
    return keep


def finalize(items, rules: Rules, today: dt.date, keep_days=75):
    out = []
    for it in items:
        if not it.get('d'):
            continue
        try:
            age = (today - dt.date.fromisoformat(it['d'])).days
        except ValueError:
            continue
        if age > keep_days or age < -3:
            continue
        it.setdefault('id', sid(f"{it['src']}|{it['url']}|{it['t']}|{it['d']}"))
        fx, tags = rules.classify(it)
        s, rk, why = rules.score(it, fx, tags, today)
        it.update(fx=fx, tags=tags, s=s, rk=rk, why=why)
        it.pop('force_tags', None)
        out.append(it)
    return sorted(out, key=lambda x: (x['d'], x['rk']), reverse=True)


def week_code(d: dt.date) -> str:
    y, w, _ = d.isocalendar()
    return f'{y % 100}.{w:02d}'
