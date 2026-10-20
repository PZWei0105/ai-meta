"""訂閱方案：人工整理的方案表（config/plans.json，每格附官方來源）＋ 匯率換算 ＋ 官方方案頁變動偵測 ＋ iOS App 版本。

方案頁多半是動態網頁，價格與額度沒辦法每次可靠地自動讀出來；所以這裡不假裝自動更新，
而是盯著官方頁面上的「價格數字」與「額度句子」：一變動（連續兩輪都一樣才算數）就標「方案頁有變，待核對」。
"""
import hashlib
import re

from .util import days_since, iso, strip_html

PRICE_TOKEN = re.compile(r'(?:US|NT)?\$\s?\d[\d,]*(?:\.\d{1,2})?')
QUOTA_SENT = re.compile(r'[^.。!?\n]{0,90}\d[^.。!?\n]{0,90}(?:messages?|hours?|per (?:day|week|month)|limits?|context|'
                        r'credits?|videos?|images?|GB|TB|requests?|queries|prompts?|則|小時|每天|每週|每月|額度)[^.。!?\n]{0,60}',
                        re.I)


def fx_rate(http, sources, health):
    for s in sources:
        try:
            d = http.json(s['url'], timeout=20)
            if s['id'] == 'er_api':
                rate, at = d['rates']['TWD'], d.get('time_last_update_utc')
            elif s['id'] == 'floatrates':
                rate, at = float(d['twd']['rate']), d['twd'].get('date')
            else:
                rate, at = float(d['usd']['twd']), d.get('date')
            rate = float(rate)
            if 25 < rate < 45:
                health['fx'] = {'ok': True, 'src': s['id']}
                return {'usd_twd': round(rate, 3), 'src': s['name'], 'at': at}
        except Exception as e:  # noqa: BLE001
            health.setdefault('fx_errors', []).append(f"{s['id']}: {type(e).__name__}")
    health['fx'] = {'ok': False}
    return None


def page_signature(html: str):
    text = strip_html(html)
    prices = sorted(set(p.replace(' ', '') for p in PRICE_TOKEN.findall(text)))
    quotas = sorted(set(re.sub(r'\s+', ' ', q.strip())[:160] for q in QUOTA_SENT.findall(text)))[:80]
    basis = '|'.join(prices) if prices else '|'.join(quotas)
    return {'prices': prices[:40], 'n_quota': len(quotas),
            'sig': hashlib.sha1(basis.encode('utf-8')).hexdigest()[:12] if basis else None,
            'basis': 'prices' if prices else 'quotas'}


def watch(http, pages: dict, prev: dict, t0, health):
    """回傳 (新狀態, 事件)。狀態：{vendor: {url: {sig, prices, basis, since, pending, pending_n, changed_at}}}"""
    out, events = {}, []
    for v, urls in pages.items():
        for url in urls:
            old = (prev.get(v) or {}).get(url) or {}
            rec = dict(old)
            try:
                html = http.text(url, timeout=30)
                sig = page_signature(html)
            except Exception as e:  # noqa: BLE001
                health.setdefault('plan_pages', {})[url] = f'{type(e).__name__}: {e}'[:120]
                out.setdefault(v, {})[url] = rec
                continue
            health.setdefault('plan_pages', {})[url] = 'ok'
            rec['checked'] = iso(t0)
            if not sig['sig']:
                out.setdefault(v, {})[url] = rec
                continue
            if not old.get('sig'):
                rec.update(sig=sig['sig'], prices=sig['prices'], basis=sig['basis'], since=iso(t0))
            elif sig['sig'] == old['sig']:
                rec.pop('pending', None)
                rec.pop('pending_n', None)
            elif sig['sig'] == old.get('pending'):
                rec['pending_n'] = old.get('pending_n', 1) + 1
                if rec['pending_n'] >= 2:
                    added = sorted(set(sig['prices']) - set(old.get('prices') or []))
                    removed = sorted(set(old.get('prices') or []) - set(sig['prices']))
                    events.append({'v': v, 'url': url, 'at': iso(t0), 'basis': sig['basis'], 'added': added,
                                   'removed': removed})
                    rec.update(sig=sig['sig'], prices=sig['prices'], basis=sig['basis'], since=iso(t0),
                               changed_at=iso(t0), added=added, removed=removed)
                    rec.pop('pending', None)
                    rec.pop('pending_n', None)
            else:
                rec['pending'], rec['pending_n'] = sig['sig'], 1
            out.setdefault(v, {})[url] = rec
    return out, events


def app_versions(http, ids: dict, health):
    out = {}
    try:
        q = ','.join(str(i) for i in ids.values())
        d = http.json(f'https://itunes.apple.com/lookup?id={q}&country=tw', timeout=20)
        by = {r.get('trackId'): r for r in d.get('results') or []}
        for v, i in ids.items():
            r = by.get(i)
            if r:
                out[v] = {'ver': r.get('version'), 'date': (r.get('currentVersionReleaseDate') or '')[:10],
                          'url': r.get('trackViewUrl', '').split('?')[0], 'rating': round(r.get('averageUserRating') or 0, 1),
                          'notes': (r.get('releaseNotes') or '')[:400]}
        health['appstore'] = {'ok': True}
    except Exception as e:  # noqa: BLE001
        health['appstore'] = {'ok': False, 'err': f'{type(e).__name__}: {e}'[:120]}
    return out


CHANGE_SHOW_DAYS = 14   # 方案頁變動的提醒掛兩週


def build(curated: dict, fx, watch_state: dict, apps: dict, t0=None):
    rate = (fx or {}).get('usd_twd')
    fee = curated.get('card_fee', 0.015)
    vendors = {}
    for v, info in curated['vendors'].items():
        plans = []
        for p in info['plans']:
            p = dict(p)
            if p.get('twd_official') is not None:            # 台灣官方台幣價（Google）：不用換算、沒有海外手續費
                p['twd'] = p['twd_card'] = p['twd_official']
            elif rate and p.get('usd') is not None:
                p['twd'] = round(p['usd'] * rate)
                p['twd_card'] = round(p['usd'] * rate * (1 + fee))
            plans.append(p)
        changed = [dict(url=u, **{k: s.get(k) for k in ('changed_at', 'added', 'removed', 'basis')})
                   for u, s in (watch_state.get(v) or {}).items()
                   if s.get('changed_at') and days_since(s['changed_at'], t0) <= CHANGE_SHOW_DAYS]
        vendors[v] = dict(info, plans=plans, page_changes=changed, app=apps.get(v))
    return {'fx': fx, 'card_fee': fee, 'checked': curated.get('checked'), 'vendors': vendors,
            'tasks': curated.get('tasks'), 'notes': curated.get('notes')}
