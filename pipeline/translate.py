"""官方英文更新紀錄 → 台灣繁體中文標題＋一兩句摘要。

和《玩真的》同一套做法：GitHub Actions 每輪在自己的伺服器上用 llama.cpp 跑開源模型（Qwen3 8B，免費、不用金鑰、
不花 Claude 額度）。結果存在 state 分支的 zh.json，同一則只翻一次；來不及翻的先顯示原文、標「翻譯中」。
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

    def one(self, source: str, title: str, body: str):
        user = f'來源：{source}\n標題：{title}\n內容：{(body or "（只有標題）")[:1000]}'
        messages = [{'role': 'system', 'content': SYSTEM}]
        for q, a in EXAMPLES:
            messages += [{'role': 'user', 'content': q}, {'role': 'assistant', 'content': a}]
        messages.append({'role': 'user', 'content': user})
        payload = {
            'messages': messages, 'temperature': 0.1, 'top_p': 0.9, 'max_tokens': 280, 'cache_prompt': True,
            'response_format': {'type': 'json_object', 'schema': SCHEMA},
            'chat_template_kwargs': {'enable_thinking': False},
        }
        r = requests.post(ENDPOINT + '/v1/chat/completions', json=payload, timeout=300)
        r.raise_for_status()
        content = r.json()['choices'][0]['message']['content'] or ''
        content = re.sub(r'(?s)<think>.*?</think>', '', content)
        data = json.loads(content[content.find('{'): content.rfind('}') + 1])
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
        src_money = set(re.findall(r'\$\s?([\d,.]+)', f'{title} {body}'))
        for mny in re.findall(r'\$\s?([\d,.]+)', f'{t} {s}'):
            if mny.rstrip('.,') not in {x.rstrip('.,') for x in src_money}:
                raise ValueError(f'金額對不上：{mny}')
        return t, s


def run(items: list[dict], st, t0, src_names: dict, budget_s: int | None = None, workers: int = 4) -> dict:
    """items 依重要性排好；直接在 item 上加 tz（中文標題）、sz（中文摘要）或 pend（翻譯中）。"""
    cache = st.load('zh.json', {})
    tr = Translator()
    stats = {'ok': tr.ok, 'model': tr.model, 'done': 0, 'cached': 0, 'failed': 0, 'pending': 0, 'secs': 0}
    need = []
    for e in items:
        if e.get('zh_native') or e.get('tz'):
            continue
        body = e.get('_tr_body') or e.get('b') or ''
        h = _h(e['t'], body[:500])
        c = cache.get(e['id'])
        if c and c.get('h') == h and c.get('v') == PROMPT_VERSION:
            e['tz'], e['sz'] = tr.tw(c['t']), (tr.tw(c.get('s')) or None)
            stats['cached'] += 1
            c['at'] = iso(t0)
        elif e.get('_translate', True):
            need.append((e, h, body))
    if tr.ok and need:
        env_budget = os.environ.get('META_LLM_BUDGET')
        budget = budget_s or (int(env_budget) if env_budget else (1500 if len(need) > 80 else 900))
        start = time.time()
        errors = []

        def job(item):
            e, h, body = item
            if time.time() - start > budget:
                return e, h, None, 'budget'
            try:
                return e, h, tr.one(src_names.get(e['src'], e['src']), e['t'], body), None
            except Exception as ex:  # noqa: BLE001 — 單則失敗就下輪再試
                return e, h, None, f'{type(ex).__name__}: {ex}'[:140]

        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for e, h, res, err in ex.map(job, need):
                if res:
                    e['tz'], e['sz'] = res[0], res[1] or None
                    cache[e['id']] = {'t': res[0], 's': res[1], 'h': h, 'at': iso(t0), 'v': PROMPT_VERSION}
                    stats['done'] += 1
                elif err != 'budget':
                    stats['failed'] += 1
                    errors.append(err)
        stats['secs'] = round(time.time() - start)
        if errors:
            stats['errors'] = errors[:5]
    for e in items:
        if not e.get('zh_native') and not e.get('tz') and e.get('_translate', True):
            e['pend'] = True
            stats['pending'] += 1
    for k in [k for k, v in cache.items() if hours_since(parse_iso(v.get('at')) or t0, t0) > 24 * KEEP_DAYS]:
        del cache[k]
    st.save('zh.json', cache)
    return stats
