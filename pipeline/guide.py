"""攻略（版本答案）：人工整理的「做什麼事用什麼」（config/playbook.json），每輪自動檢查有沒有過時。

過時訊號（固定規則）：
1. 答案裡指定的雲端模型已停用、或同一家族出了更新的版本。
2. 答案裡指定的本機模型不在精選清單了。
3. 最近 21 天有相關的重大改版（同一家、相關標籤、新增／移除／加強／削弱、分數 35 以上）。
4. 超過 45 天沒有人工複查。
"""
import datetime as dt

from .util import days_since


def evaluate(playbook: dict, models: list, local_ids: set, patches: list, today: dt.date):
    by_id = {m['id']: m for m in models}
    main_by_fam = {(m['v'], m.get('fam')): m for m in models if m.get('main')}
    reviewed = playbook.get('reviewed')
    out_tasks = []
    for task in playbook.get('tasks', []):
        task = dict(task)
        flags = []
        for p in task.get('picks', []):
            for mid in p.get('models') or []:
                m = by_id.get(mid)
                if m is None:
                    flags.append({'type': 'missing', 'text': f'價格表找不到 {mid}，可能改名或下架'})
                    continue
                if m.get('status') in ('deprecated', 'retired'):
                    flags.append({'type': 'retired', 'text': f"{m['name']} 已列入停用"})
                newer = main_by_fam.get((m['v'], m.get('fam')))
                if newer and newer['id'] != m['id'] and (newer.get('ver') or 0) > (m.get('ver') or 0):
                    flags.append({'type': 'newer', 'text': f"同家族出了 {newer['name']}"})
            lid = p.get('local_id')
            if lid and lid not in local_ids:
                flags.append({'type': 'local_missing', 'text': f'本機精選清單已移除 {lid}'})
        w = task.get('watch') or {}
        hits = []
        for it in patches:
            if it.get('v') not in (w.get('vendors') or []):
                continue
            if not set(it.get('tags') or []) & set(w.get('tags') or []):
                continue
            if it.get('fx') not in ('new', 'gone', 'buff', 'nerf') or it.get('s', 0) < 35:
                continue
            if (today - dt.date.fromisoformat(it['d'])).days > 21:
                continue
            if reviewed and it['d'] <= reviewed:
                continue
            hits.append({'id': it['id'], 't': it.get('tz') or it['t'], 'd': it['d'], 'fx': it['fx'], 'v': it['v']})
        if hits:
            flags.append({'type': 'patch', 'text': f'複查後又有 {len(hits)} 則相關改版', 'items': hits[:3]})
        age = days_since(task.get('reviewed') or reviewed, dt.datetime.combine(today, dt.time(12), dt.timezone.utc))
        if age > 45:
            flags.append({'type': 'old', 'text': f'已經 {int(age)} 天沒複查'})
        task['flags'] = flags
        task['fresh'] = 'stale' if any(f['type'] in ('retired', 'newer', 'missing', 'local_missing') for f in flags) \
            else 'watch' if flags else 'fresh'
        out_tasks.append(task)
    return dict(playbook, tasks=out_tasks)
