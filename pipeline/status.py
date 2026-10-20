"""四家伺服器狀態：官方狀態頁的公開資料（Claude、OpenAI 是 Statuspage 格式；xAI 有自己的 JSON；
Google 沒有 Gemini App 的公開狀態頁，只看 Google Cloud 上 Gemini API 的事故）。"""
import datetime as dt

from .util import days_since, iso, parse_iso

LEVEL = {'none': 'ok', 'minor': 'minor', 'major': 'major', 'critical': 'critical', 'maintenance': 'minor'}
RANK = {'ok': 0, 'minor': 1, 'major': 2, 'critical': 3, 'unknown': -1}
COMP_BAD = {'degraded_performance': 'minor', 'partial_outage': 'major', 'major_outage': 'critical',
            'under_maintenance': 'minor'}
# 只顯示跟 PZ 有關的元件（其餘照樣影響整體燈號）
KEEP = {
    'claude': ['claude.ai', 'Claude Code', 'Claude API', 'Claude Console', 'Cowork'],
    'chatgpt': ['ChatGPT', 'Codex', 'Image Generation', 'Deep Research', 'Voice mode', 'Login', 'Responses',
                'Search', 'File uploads', 'Agent'],
    'grok': ['grok.com', 'grok', 'api', 'imagine', 'voice'],
}


def _recent(incidents, t0, days=7):
    out = []
    for i in incidents:
        start = parse_iso(i.get('created_at') or i.get('begin'))
        if not start or (t0 - start).days > days:
            continue
        end = parse_iso(i.get('resolved_at') or i.get('end'))
        out.append({'t': i.get('name') or i.get('external_desc') or '', 'impact': LEVEL.get(i.get('impact') or
                    i.get('severity') or 'minor', 'minor'), 'at': iso(start), 'end': iso(end) if end else None,
                    'mins': int((end - start).total_seconds() / 60) if end else None,
                    'url': i.get('shortlink') or i.get('uri') or None})
    return sorted(out, key=lambda x: x['at'], reverse=True)


def statuspage(v, summary, incidents, t0, page_url):
    ind = LEVEL.get(((summary or {}).get('status') or {}).get('indicator') or 'none', 'unknown')
    comps = []
    for c in (summary or {}).get('components') or []:
        if c.get('group'):
            continue
        name = c.get('name') or ''
        keep = any(k.lower() in name.lower() for k in KEEP.get(v, []))
        st = COMP_BAD.get(c.get('status'), 'ok')
        if (keep or st != 'ok') and name not in [x['n'] for x in comps]:
            comps.append({'n': name, 's': st})
    active = [i for i in (summary or {}).get('incidents') or [] if i.get('status') not in ('resolved', 'postmortem')]
    recent = _recent((incidents or {}).get('incidents') or [], t0)
    act = [{'t': i.get('name'), 'impact': LEVEL.get(i.get('impact') or 'minor', 'minor'),
            'at': i.get('created_at'), 'url': i.get('shortlink')} for i in active]
    if act and RANK.get(ind, 0) == 0:
        ind = max((a['impact'] for a in act), key=lambda x: RANK[x])
    return {'v': v, 'ind': ind, 'comps': comps[:10], 'active': act, 'recent': recent[:8], 'n7': len(recent),
            'page': page_url, 'src': 'official'}


def xai(incidents, uptime, t0):
    inc = (incidents or {}).get('incidents') or []
    active = [i for i in inc if i.get('status') not in ('resolved', 'postmortem')]
    ind = 'ok'
    for i in active:
        lv = LEVEL.get(i.get('impact') or 'minor', 'minor')
        if RANK[lv] > RANK[ind]:
            ind = lv
    comps = []
    today = t0.date().isoformat()
    names = {'grok-com': 'grok.com', 'ios-app': 'iOS App', 'android-app': 'Android App', 'grok-in-x': 'X 裡的 Grok',
             'imagine': 'Imagine 生圖／影片', 'voice': '語音', 'api-global': 'API'}
    bad_ids = {c for i in active for c in (i.get('incident_updates') or [{}])[0].get('affected_components') or []}
    for c in (uptime or {}).get('components') or []:
        cid = c.get('id', '')
        if cid not in names:
            continue
        hist = c.get('history') or []
        last = hist[-1] if hist else {}
        st = 'ok'
        if cid in bad_ids:
            st = ind if ind != 'ok' else 'minor'
        elif last.get('day') == today and last.get('status') not in (None, 'available', 'operational'):
            st = 'minor'
        comps.append({'n': names[cid], 's': st})
    act = [{'t': i.get('name'), 'impact': LEVEL.get(i.get('impact') or 'minor', 'minor'), 'at': i.get('created_at')}
           for i in active]
    return {'v': 'grok', 'ind': ind, 'comps': comps[:8], 'active': act, 'recent': _recent(inc, t0)[:8],
            'n7': len(_recent(inc, t0)), 'page': 'https://status.x.ai/', 'src': 'official'}


def google(gcloud, t0):
    inc = [i for i in gcloud or [] if any('gemini' in (p.get('title') or '').lower()
                                           for p in i.get('affected_products') or [])]
    recent = _recent(inc, t0, days=7)
    active = [i for i in inc if not i.get('end')]
    ind = 'ok'
    for i in active:
        lv = {'low': 'minor', 'medium': 'major', 'high': 'critical'}.get(i.get('severity'), 'minor')
        if RANK[lv] > RANK[ind]:
            ind = lv
    act = [{'t': i.get('external_desc', '')[:160], 'impact': ind, 'at': i.get('begin'),
            'url': 'https://status.cloud.google.com/' + (i.get('uri') or '')} for i in active]
    return {'v': 'gemini', 'ind': ind, 'comps': [{'n': 'Gemini API（Google Cloud）', 's': ind}], 'active': act,
            'recent': recent[:8], 'n7': len(recent), 'page': 'https://aistudio.google.com/status',
            'src': 'gcloud', 'note': 'Google 沒有公開 Gemini App 的狀態資料，這裡只看 Google Cloud 上 Gemini API 的事故。'}


def unknown(v, page, err):
    return {'v': v, 'ind': 'unknown', 'comps': [], 'active': [], 'recent': [], 'n7': None, 'page': page,
            'src': 'none', 'err': err}


def freshness_ok(item, t0, hours=3):
    at = parse_iso(item.get('at'))
    return at is not None and days_since(at, t0) * 24 <= hours


__all__ = ['statuspage', 'xai', 'google', 'unknown', 'freshness_ok', 'dt']
