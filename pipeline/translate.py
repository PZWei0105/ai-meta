"""官方英文更新紀錄 → 台灣繁體中文標題＋一兩句摘要。

和《玩真的》同一套做法：GitHub Actions 每輪在自己的伺服器上用 llama.cpp 跑開源模型（Qwen3 8B，免費、不用金鑰、
不花 Claude 額度）。結果存在 state 分支的 zh.json，同一則只翻一次。

PZ 的要求：資訊一律先翻成繁體中文才上架。所以：
- 還沒翻好的改版不會出現在 App（標 pend，App 只顯示「還有幾則翻譯中」）；
- 內容改了（例如每週合併的工具更新多了一版）先沿用上一次的中文，背景重翻；
- 除了標題＋摘要，再把內容逐點翻成中文條列（points），展開卡片時顯示，不再露出英文原文；
- 伺服器狀態頁的事故標題、服務名稱也翻（short）。
"""
import concurrent.futures as cf
import hashlib
import json
import os
import re
import time

import requests

from .util import hours_since, iso, parse_iso

ENDPOINT = os.environ.get('META_LLM', 'http://127.0.0.1:8088')
KEEP_DAYS = 120
PROMPT_VERSION = 1   # 改了提示詞或模型就加一，舊翻譯會重翻
POINTS_VERSION = 1
SHORT_VERSION = 1
TIMEOUT = 300

SYSTEM = """你是台灣科技媒體的 AI 產品編輯。把官方英文更新紀錄整理成台灣繁體中文，只輸出 JSON：{"title": 中文標題, "summary": 中文摘要}。

規則：
1. 產品名、模型名、方案名、功能專有名詞、公司名照抄英文原文，不要翻譯、不要加書名號：例如 Claude Code、Codex、ChatGPT Pro、Max、GPT-6.1 Sol、Gemini 4 Argon、Fast mode、Deep Research。
2. title：28 字以內，直接講發生什麼事（新增、調整、停用、降價、漲價、修正）。
3. summary：1 到 2 句、30 到 90 字。只能寫內容裡有的事實，不可補充、推測、評論或下結論；不要寫「這將會」「讓使用者更方便」這類空話。
4. 數字、價格、日期、版本號必須和原文一致；$ 金額照抄（例如 $2、$0.10）。日期寫成「10 月 15 日」。
5. 用台灣用語：方案、額度、上下文、token、影片、軟體、程式碼、設定、支援、外掛、專案、桌面版、行動裝置、介面、記憶體。不要用簡體字或對岸用語。"""

EXAMPLES = [
    ('來源：Claude App 更新紀錄\n標題：Monthly API credits for Max and Team plans\n內容：Max and Team plans now include monthly API credits for running your own apps and agents on the Claude Platform. They roll out over a few days. Claim them by linking a Claude Console organization in Settings > Billing.',
     '{"title": "Max 與 Team 方案每月附贈 API 額度", "summary": "Max 與 Team 方案開始每月附贈 Claude Platform 的 API 額度，可用來跑自己的 App 和代理，接下來幾天陸續開放；要在設定的帳單頁連結 Claude Console 組織才能領取。"}'),
    ('來源：Gemini API 更新紀錄\n標題：Gemini 3.7 Flash deprecation\n內容：gemini-3.7-flash is deprecated and has been replaced by gemini-3.8-flash. API requests to gemini-3.7-flash are automatically routed to gemini-3.8-flash.',
     '{"title": "Gemini 3.7 Flash 停用，改由 3.8 Flash 接手", "summary": "gemini-3.7-flash 已停用，由 gemini-3.8-flash 取代；送往 gemini-3.7-flash 的 API 請求會自動轉到 gemini-3.8-flash。"}'),
    ('來源：Claude Code 版本更新\n標題：Claude Code 2.1.304\n內容：重點：Added a warning on Pro and Max plans when resuming an inactive conversation would use a noticeable share of your 5-hour usage limit. Added /auto-mode-setup: a guided setup that reads your project to teach auto mode about your environment.',
     '{"title": "Claude Code 2.1.304：接續舊對話前先提醒額度", "summary": "Pro 與 Max 方案接續閒置的舊對話、會吃掉不少 5 小時額度時，會先跳出提醒；另外新增 /auto-mode-setup 引導設定 auto mode。"}'),
]

SCHEMA = {'type': 'object', 'properties': {'title': {'type': 'string'}, 'summary': {'type': 'string'}},
          'required': ['title', 'summary']}

SYSTEM_POINTS = """你是台灣科技媒體的 AI 產品編輯。把官方英文更新紀錄的內容逐點整理成台灣繁體中文條列，只輸出 JSON：{"points": [每一點一句中文]}。

規則：
1. 最多 5 點，每點 15 到 70 字，一點講一件事；照原文順序，挑最重要的。
2. 只能寫內容裡有的事實，不可補充、推測、評論或下結論。
3. 產品名、模型名、方案名、指令、設定名稱、環境變數照抄英文原文（例如 Claude Code、/usage、CLAUDE_CODE_AUTO_MODE_MODEL）。
4. 數字、價格、日期、版本號必須和原文一致；$ 金額照抄。
5. 用台灣用語：方案、額度、上下文、影片、軟體、程式碼、設定、支援、外掛、專案。不要用簡體字或對岸用語。"""

EXAMPLES_POINTS = [
    ('來源：Claude Code 版本更新\n標題：Claude Code 2.1.304\n內容：Added a warning on Pro and Max plans when resuming an inactive conversation would use a noticeable share of your 5-hour usage limit. Improved /usage to say when a rate limit on usage data ends instead of "try again in a moment". Fixed a crash when pasting large images on Windows.',
     '{"points": ["Pro 與 Max 方案接續閒置的舊對話、會吃掉不少 5 小時額度時，會先跳出提醒", "/usage 會直接顯示用量資料的限制什麼時候結束，不再只寫「稍後再試」", "修正 Windows 上貼上大型圖片時當機的問題"]}'),
]
SCHEMA_POINTS = {'type': 'object', 'properties': {'points': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 5}},
                 'required': ['points']}

SYSTEM_SHORT = """把 AI 服務狀態頁上的英文短句翻成台灣繁體中文，只輸出 JSON：{"zh": 中文}。
產品名、模型名、功能專有名詞照抄英文（例如 ChatGPT、Codex、Claude Code、API、Sora、Deep Research）。不加句號、不加解釋，24 字以內，用台灣用語。"""
EXAMPLES_SHORT = [
    ('Elevated error rates on Claude Opus 5.5', '{"zh": "Claude Opus 5.5 錯誤率升高"}'),
    ('File Download errors', '{"zh": "檔案下載出錯"}'),
    ('Voice mode', '{"zh": "語音模式"}'),
]
SCHEMA_SHORT = {'type': 'object', 'properties': {'zh': {'type': 'string'}}, 'required': ['zh']}
TERMS = [('克隆', '複製'), ('存儲', '儲存'), ('視頻', '影片'), ('軟件', '軟體'), ('硬件', '硬體'), ('網絡', '網路'),
         ('質量', '品質'), ('信息', '資訊'), ('用戶', '使用者'), ('服務器', '伺服器'), ('鼠標', '滑鼠'), ('屏幕', '螢幕'),
         ('默認', '預設'), ('數據', '資料'), ('代碼', '程式碼'), ('程序', '程式'), ('內存', '記憶體'), ('顯存', '顯示記憶體'),
         ('支持', '支援'), ('設置', '設定'), ('插件', '外掛'), ('集成', '整合'), ('鏈接', '連結'), ('登錄', '登入'),
         ('界面', '介面'), ('在線', '線上'), ('移動端', '行動裝置'), ('桌面端', '桌面版'), ('令牌', 'token'),
         ('上下文窗口', '上下文長度'), ('智能體', '代理'), ('訂閱計劃', '訂閱方案'), ('計劃', '方案'), ('文檔', '文件'),
         ('圖像', '圖片'), ('臺灣', '台灣'), ('項目', '專案'), ('高級', '進階'), ('調用', '呼叫'), ('運行', '執行'),
         ('部署', '部署'), ('賬號', '帳號'), ('帳户', '帳戶'), ('社區', '社群'), ('博客', '部落格'), ('發布', '發布')]
SIMPLIFIED_ONLY = set('们这个时会对发现经过还没进开关间问题实现为与业务东车长门马鸟龙认识让请谁说读调网络视频软件硬件质数据库设计应该样么见观觉专产团队导岁华实际战类级线乐亲传标签载输设备优惠币购买卖费钱额')
SPEC = re.compile(r'(這將|將會讓|讓使用者更|大幅提升|更加方便|值得期待|帶來更好)')


def _h(*parts) -> str:
    return hashlib.sha1('\n'.join(p or '' for p in parts).encode('utf-8')).hexdigest()[:10]


class Translator:
    def __init__(self):
        self.ok = self._alive()
        self.model = os.environ.get('META_LLM_MODEL', '')
        try:
            from opencc import OpenCC
            self.to_tw = OpenCC('s2twp')
        except Exception:  # noqa: BLE001
            self.to_tw = None

    @staticmethod
    def _alive() -> bool:
        try:
            return requests.get(ENDPOINT + '/health', timeout=5).status_code == 200
        except requests.RequestException:
            return False

    def tw(self, s: str) -> str:
        s = re.sub(r'\s+', ' ', (s or '').strip())
        if len(s) >= 2 and s[0] in '"“「『' and s[-1] in '"”」』':
            s = s[1:-1].strip()
        if self.to_tw and any(ch in SIMPLIFIED_ONLY for ch in s):
            s = self.to_tw.convert(s)
        for a, b in TERMS:
            s = s.replace(a, b)
        return s

    @staticmethod
    def _ask(system, examples, user, schema, max_tokens, timeout=TIMEOUT):
        messages = [{'role': 'system', 'content': system}]
        for q, a in examples:
            messages += [{'role': 'user', 'content': q}, {'role': 'assistant', 'content': a}]
        messages.append({'role': 'user', 'content': user})
        payload = {
            'messages': messages, 'temperature': 0.1, 'top_p': 0.9, 'max_tokens': max_tokens, 'cache_prompt': True,
            'response_format': {'type': 'json_object', 'schema': schema},
            'chat_template_kwargs': {'enable_thinking': False},
        }
        r = requests.post(ENDPOINT + '/v1/chat/completions', json=payload, timeout=timeout)
        r.raise_for_status()
        content = r.json()['choices'][0]['message']['content'] or ''
        content = re.sub(r'(?s)<think>.*?</think>', '', content)
        return json.loads(content[content.find('{'): content.rfind('}') + 1])

    def warm(self, workers: int):
        """先讓每個平行通道把固定的說明＋範例讀進快取；不然第一批同時開跑會一起卡到逾時。"""
        def go(i):
            try:
                self._ask(SYSTEM, EXAMPLES, f'來源：測試\n標題：Warm up {i}\n內容：（只有標題）', SCHEMA, 8, timeout=900)
            except Exception:  # noqa: BLE001
                pass
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(go, range(workers)))

    @staticmethod
    def _money_ok(src_text: str, out_text: str):
        src_money = {x.rstrip('.,') for x in re.findall(r'\$\s?([\d,.]+)', src_text)}
        for mny in re.findall(r'\$\s?([\d,.]+)', out_text):
            if mny.rstrip('.,') not in src_money:
                raise ValueError(f'金額對不上：{mny}')

    def points(self, source: str, title: str, body: str):
        user = f'來源：{source}\n標題：{title}\n內容：{(body or "")[:1400]}'
        data = self._ask(SYSTEM_POINTS, EXAMPLES_POINTS, user, SCHEMA_POINTS, 420)
        out = []
        for p in data.get('points') or []:
            p = self.tw(p).rstrip('。；;')
            if SPEC.search(p) or len(re.findall(r'[一-鿿]', p)) < 4 or len(p) > 140:
                continue
            out.append(p)
        if not out:
            raise ValueError('條列不合格')
        self._money_ok(f'{title} {body}', ' '.join(out))
        return out[:5]

    def short(self, text: str):
        data = self._ask(SYSTEM_SHORT, EXAMPLES_SHORT, text[:200], SCHEMA_SHORT, 60, timeout=120)
        z = self.tw(data.get('zh', '')).rstrip('。')
        if not z or len(z) > 60:
            raise ValueError(f'短句不合格：{z[:30]}')
        if not re.search(r'[一-鿿]', z) and re.sub(r'\W', '', z.lower()) != re.sub(r'\W', '', text.lower()):
            raise ValueError(f'短句沒翻：{z[:30]}')   # 沒有中文時，只接受「原樣照抄」的產品名
        return z

    def one(self, source: str, title: str, body: str):
        user = f'來源：{source}\n標題：{title}\n內容：{(body or "（只有標題）")[:1000]}'
        data = self._ask(SYSTEM, EXAMPLES, user, SCHEMA, 280)
        t = self.tw(data.get('title', '')).rstrip('。')
        s = self.tw(data.get('summary', ''))
        if len(re.findall(r'[一-鿿]', t)) < 2 or not 2 <= len(t) <= 80:
            if len(title) <= 60:
                t = title
            else:
                raise ValueError(f'標題不合格：{t[:40]}')
        if s:
            parts = [p for p in re.split(r'(?<=[。！？])', s) if p and not SPEC.search(p)]
            s = ''.join(parts).strip()
            if len(re.findall(r'[一-鿿]', s)) < 8 or len(s) > 260:
                s = ''
        # 數字守門：原文出現的金額，譯文裡若出現 $ 就必須是原文有的數字
        self._money_ok(f'{title} {body}', f'{t} {s}')
        return t, s


def _needs_points(e, body: str) -> bool:
    """內容比摘要多很多時才逐點翻（只有一兩句的公告，摘要就夠了）。"""
    if e.get('zh_native'):
        return False
    if e.get('tool') and len(e.get('hl') or []) >= 2:
        return True
    return len(body or '') >= 200


def run(items: list[dict], st, t0, src_names: dict, budget_s: int | None = None, workers: int = 4,
        shorts: list[str] | None = None) -> dict:
    """items 依重要性排好；直接在 item 上加 tz（中文標題）、sz（中文摘要）、pts（中文條列）或 pend（翻譯中）。

    shorts：伺服器狀態的事故標題、服務名稱這類短句；翻好的對照表放在回傳值的 short_map。
    """
    cache = st.load('zh.json', {})
    scache = st.load('zh_short.json', {})
    tr = Translator()
    stats = {'ok': tr.ok, 'model': tr.model, 'done': 0, 'cached': 0, 'failed': 0, 'pending': 0, 'secs': 0,
             'points': 0, 'short': 0}
    need, need_pts = [], []
    for e in items:
        if e.get('zh_native'):
            continue
        body = e.get('_tr_body') or e.get('b') or ''
        pbody = ('重點：' + '；'.join(e['hl'])) if e.get('tool') and e.get('hl') else (e.get('b') or '')
        h = _h(e['t'], body[:500])
        ph = _h(e['t'], pbody[:900])
        c = cache.get(e['id'])
        if c and c.get('v') == PROMPT_VERSION:
            e['tz'], e['sz'] = tr.tw(c['t']), (tr.tw(c.get('s')) or None)   # 內容改了也先沿用上一次的中文
            c['at'] = iso(t0)
            if c.get('h') == h:
                stats['cached'] += 1
            elif e.get('_translate', True):
                need.append((e, h, body))
            if c.get('p') and c.get('pv') == POINTS_VERSION:
                e['pts'] = [tr.tw(x) for x in c['p']]
            if (c.get('ph') != ph or c.get('pv') != POINTS_VERSION) and _needs_points(e, pbody):
                need_pts.append((e, ph, pbody))
        elif e.get('_translate', True):
            need.append((e, h, body))
            if _needs_points(e, pbody):
                need_pts.append((e, ph, pbody))
    short_map, need_short = {}, []
    for text in dict.fromkeys(x for x in (shorts or []) if x and re.search(r'[A-Za-z]', x)):
        k = _h(text)
        c = scache.get(k)
        if c and c.get('v') == SHORT_VERSION:
            short_map[text] = c['zh']
            c['at'] = iso(t0)
        else:
            need_short.append((text, k))

    if tr.ok and (need or need_pts or need_short):
        env_budget = os.environ.get('META_LLM_BUDGET')
        budget = budget_s or (int(env_budget) if env_budget else (2400 if len(need) + len(need_pts) > 60 else 900))
        start = time.time()
        errors = []
        tr.warm(workers)

        def left():
            return budget - (time.time() - start)

        def job(item):
            e, h, body = item
            if left() <= 0:
                return e, h, None, 'budget'
            try:
                return e, h, tr.one(src_names.get(e['src'], e['src']), e['t'], body), None
            except Exception as ex:  # noqa: BLE001 — 單則失敗就下輪再試
                return e, h, None, f'{type(ex).__name__}: {ex}'[:140]

        def save(e, h, res):
            e['tz'], e['sz'] = res[0], res[1] or None
            old = cache.get(e['id']) or {}
            cache[e['id']] = dict(old, t=res[0], s=res[1], h=h, at=iso(t0), v=PROMPT_VERSION)
            e.pop('pend', None)
            stats['done'] += 1

        # 1. 標題＋摘要（逾時的放到最後再試一次，那時候快取已經暖好）
        retry = []
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for e, h, res, err in ex.map(job, need):
                if res:
                    save(e, h, res)
                elif err and err != 'budget':
                    (retry if 'Timeout' in err else errors).append((e, h, err))
            if retry and left() > 60:
                for e, h, res, err in ex.map(job, [(e, h, b) for e, h, b in need if any(e is r[0] for r in retry)]):
                    if res:
                        save(e, h, res)
                    elif err and err != 'budget':
                        errors.append((e, h, err))
            else:
                errors += retry

        # 2. 伺服器狀態的短句
        def sjob(item):
            text, k = item
            if left() <= 0:
                return text, k, None
            try:
                return text, k, tr.short(text)
            except Exception:  # noqa: BLE001
                return text, k, None
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for text, k, z in ex.map(sjob, need_short):
                if z:
                    short_map[text] = z
                    scache[k] = {'zh': z, 'at': iso(t0), 'v': SHORT_VERSION}
                    stats['short'] += 1

        # 3. 內容逐點翻（只翻已經有中文標題的，先翻重要的）
        def pjob(item):
            e, ph, body = item
            if left() <= 0 or not e.get('tz'):
                return e, ph, None, 'budget'
            try:
                return e, ph, tr.points(src_names.get(e['src'], e['src']), e['t'], body), None
            except Exception as ex:  # noqa: BLE001
                return e, ph, None, f'{type(ex).__name__}: {ex}'[:140]
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for e, ph, pts, err in ex.map(pjob, need_pts):
                if pts:
                    e['pts'] = pts
                    c = cache.get(e['id'])
                    if c:
                        c.update(p=pts, ph=ph, pv=POINTS_VERSION)
                    stats['points'] += 1
                elif err and err != 'budget':
                    errors.append((e, ph, err))

        stats['secs'] = round(time.time() - start)
        stats['failed'] = len(errors)
        if errors:
            stats['errors'] = [x[2] for x in errors[:5]]
    for e in items:
        if not e.get('zh_native') and not e.get('tz') and e.get('_translate', True):
            e['pend'] = True
            stats['pending'] += 1
    stats['points_pending'] = sum(1 for e, _, _ in need_pts if not e.get('pts'))
    for k in [k for k, v in cache.items() if hours_since(parse_iso(v.get('at')) or t0, t0) > 24 * KEEP_DAYS]:
        del cache[k]
    for k in [k for k, v in scache.items() if hours_since(parse_iso(v.get('at')) or t0, t0) > 24 * 30]:
        del scache[k]
    st.save('zh.json', cache)
    st.save('zh_short.json', scache)
    stats['short_map'] = short_map
    return stats
