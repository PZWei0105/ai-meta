"""每小時一輪：抓官方更新紀錄、價格表、狀態頁、匯率、Hugging Face → 分類、評分、翻譯、檢查攻略 → 輸出 App 資料。"""
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import time
import traceback

from . import feeds, guide, local, patches, plans, prices, status
from .state import State, write_json
from .util import TW, Http, iso, now

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_FILES = ('meta.json', 'patches.json', 'prices.json', 'status.json', 'plans.json', 'local.json', 'guide.json')
SHOW_DAYS = 60
TRANSLATE_DAYS = SHOW_DAYS     # App 只顯示翻好的，所以看得到的範圍全部都要翻


def cfg(name):
    return json.loads((ROOT / 'config' / name).read_text(encoding='utf-8'))


def copy_site(out_dir: pathlib.Path):
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(ROOT / 'site', out_dir, ignore=shutil.ignore_patterns('data'))
    h = hashlib.sha1()
    for p in sorted((ROOT / 'site').rglob('*')):
        if p.is_file() and 'data' not in p.relative_to(ROOT / 'site').parts:
            h.update(p.read_bytes())
    build_id = h.hexdigest()[:10]
    for name in ('sw.js', 'index.html'):
        f = out_dir / name
        if f.exists():
            f.write_text(f.read_text(encoding='utf-8').replace('__BUILD__', build_id), encoding='utf-8')
    return build_id


# ------------------------------------------------------------------ 改版公告
def fetch_patch_source(http, src, today):
    k = src['kind']
    if k == 'claude_code':
        md = http.text(src['url'], timeout=40)
        npm = http.json(src['npm'], timeout=40)
        return feeds.claude_code(src, md, npm)
    if k == 'gh_releases':
        data = http.json(f"https://api.github.com/repos/{src['repo']}/releases?per_page=15", timeout=40)
        return feeds.gh_releases(src, data)
    if k == 'rss':
        r = http.get(src['url'], timeout=40)
        if r.status_code != 200:
            raise RuntimeError(f'HTTP {r.status_code}')
        return feeds.rss(src, r.content)
    text = http.text(src['url'], timeout=40)
    if k == 'md_dated':
        return feeds.md_dated(src, text)
    if k == 'md_month':
        return feeds.md_month(src, text, today)
    if k == 'intercom':
        return feeds.intercom(src, text)
    if k == 'help_dated':
        return feeds.help_dated(src, text)
    if k == 'gemini_app':
        return feeds.gemini_app(src, text)
    if k == 'openai_changelog':
        return feeds.openai_changelog(src, text, today)
    if k == 'anthropic_news':
        return feeds.anthropic_news(src, text)
    if k == 'xai_news':
        return feeds.xai_news(src, text)
    if k == 'lmstudio':
        return feeds.lmstudio(src, text)
    if k == 'nvidia':
        return feeds.nvidia(src, text)
    raise ValueError(f'unknown kind {k}')


def collect_patches(http, st, sources, today, health):
    saved = st.load('feeds.json.gz', {})
    got = {}

    def one(src):
        start = time.time()
        try:
            return src['id'], fetch_patch_source(http, src, today), None, time.time() - start
        except Exception as e:  # noqa: BLE001 — 單一來源失敗不影響其他來源
            return src['id'], None, f'{type(e).__name__}: {e}'[:200], time.time() - start

    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for sid_, items, err, secs in ex.map(one, sources):
            h = health.setdefault('patches', {}).setdefault(sid_, {})
            h['ms'] = int(secs * 1000)
            if items:
                recent = [x for x in items if x.get('d') and (today - dt.date.fromisoformat(x['d'])).days <= SHOW_DAYS + 15]
                got[sid_] = recent
                saved[sid_] = {'at': iso(now()), 'items': recent}
                h.update(ok=True, n=len(recent), err=None, last_ok=iso(now()))
            else:
                old = saved.get(sid_) or {}
                got[sid_] = old.get('items') or []
                h.update(ok=False, n=len(got[sid_]), err=err or '解析不到任何項目', last_ok=old.get('at'))
    st.save('feeds.json.gz', saved)
    return [x for items in got.values() for x in items]


# ------------------------------------------------------------------ API 價格
def collect_prices(http, st, srcs, t0, health):
    hp = health.setdefault('prices', {})
    texts = {}
    for k, url in srcs.items():
        try:
            texts[k] = http.text(url, timeout=40) if k != 'openrouter' else http.json(url, timeout=40)
            hp[k] = 'ok'
        except Exception as e:  # noqa: BLE001
            hp[k] = f'{type(e).__name__}: {e}'[:120]
    saved = st.load('prices_raw.json', {})
    models = []
    for v, fn in (('claude', lambda: prices.claude(texts['claude_pricing'], texts['claude_deprecations'],
                                                    texts.get('claude_models', ''))[0]),
                  ('gemini', lambda: prices.gemini(texts['gemini_pricing'], texts.get('gemini_deprecations', ''))[0]),
                  ('chatgpt', lambda: prices.openai(texts['openai_pricing'], texts.get('openai_deprecations', ''))[0]),
                  ('grok', lambda: prices.xai(texts['xai_pricing']))):
        try:
            ms = prices.check_sane(fn())
            if not ms:
                raise ValueError('解析不到任何模型')
            saved[v] = {'at': iso(t0), 'models': ms}
            hp[f'parse_{v}'] = f'ok ({len(ms)})'
        except Exception as e:  # noqa: BLE001
            hp[f'parse_{v}'] = f'{type(e).__name__}: {e}'[:120]
            ms = (saved.get(v) or {}).get('models') or []
            for m in ms:
                m['stale'] = True
        models.extend(ms)
    st.save('prices_raw.json', saved)
    models = prices.cross_check(models, (texts.get('openrouter') or {}).get('data') if isinstance(texts.get('openrouter'), dict) else None)
    tiers = cfg('lineup.json')
    prices.mark_main(models, tiers.get('tiers', {}))
    for m in models:
        fam_note = (tiers.get('family_notes', {}).get(m['v']) or {}).get(m.get('fam'))
        if fam_note:
            m['role'] = fam_note
    prev = st.load('prices_state.json', {})
    nxt, events = prices.diff(models, prev, t0)
    held = [f"{m['v']}/{m['id']}" for m in models if m.get('held')]
    if held:
        hp['held'] = held          # 官方頁讀到的價跟 OpenRouter 對不上，先沿用舊價
    st.save('prices_state.json', nxt)
    # 價格異動、新模型上架要在「改版」裡留著（以前只出現在偵測到的那一輪，一小時後就不見了）
    ekey = lambda e: (e['v'], e['id'], e['type'], e.get('field'), e['at'])  # noqa: E731
    log = [e for e in st.load('price_events.json', []) if (t0 - dt.datetime.fromisoformat(
        e['at'].replace('Z', '+00:00'))).days <= SHOW_DAYS]
    seen = {ekey(e) for e in log}
    log += [e for e in events if ekey(e) not in seen]
    st.save('price_events.json', log)
    up = prices.upcoming(models, t0.astimezone(TW).date())
    return models, log, up


# ------------------------------------------------------------------ 伺服器狀態
def collect_status(http, srcs, t0, health):
    out = {}
    hs = health.setdefault('status', {})

    def get(url):
        try:
            return http.json(url, timeout=25)
        except Exception as e:  # noqa: BLE001
            hs[url] = f'{type(e).__name__}: {e}'[:100]
            return None

    s1, i1 = get(srcs['claude_summary']), get(srcs['claude_incidents'])
    out['claude'] = status.statuspage('claude', s1, i1, t0, 'https://status.claude.com') if s1 else \
        status.unknown('claude', 'https://status.claude.com', '狀態頁暫時讀不到')
    s2, i2 = get(srcs['openai_summary']), get(srcs['openai_incidents'])
    out['chatgpt'] = status.statuspage('chatgpt', s2, i2, t0, 'https://status.openai.com') if s2 else \
        status.unknown('chatgpt', 'https://status.openai.com', '狀態頁暫時讀不到')
    g = get(srcs['gcloud_incidents'])
    out['gemini'] = status.google(g, t0) if g is not None else \
        status.unknown('gemini', 'https://aistudio.google.com/status', '狀態頁暫時讀不到')
    xi, xu = get(srcs['xai_incidents']), get(srcs['xai_uptime'])
    out['grok'] = status.xai(xi, xu, t0) if xi is not None else \
        status.unknown('grok', 'https://status.x.ai/', '狀態頁暫時讀不到')
    for v in out.values():
        v['at'] = iso(t0)
    return out


# ------------------------------------------------------------------ 一輪完整流程
def execute(http, st: State, t0, data_dir: pathlib.Path, build_id: str):
    errors = []
    health = {}
    today = t0.astimezone(TW).date()
    src_cfg = cfg('sources.json')
    profile = cfg('profile.json')
    rules = patches.Rules(cfg('rules.json'), profile)
    rig = dict(profile['rig'])

    # 1. 改版公告
    items = []
    try:
        items = collect_patches(http, st, src_cfg['patches'], today, health)
    except Exception:  # noqa: BLE001
        errors.append('patches: ' + traceback.format_exc()[-400:])
        traceback.print_exc()

    # 2. API 價格
    models, price_events, upcoming = [], [], []
    try:
        models, price_events, upcoming = collect_prices(http, st, src_cfg['prices'], t0, health)
        page_urls = {v: info.get('api_pricing') for v, info in src_cfg['vendors'].items()}
        items += patches.price_items(price_events, today, page_urls)
    except Exception:  # noqa: BLE001
        errors.append('prices: ' + traceback.format_exc()[-400:])
        traceback.print_exc()

    # 3. 每天更新的工具一週併一則；分類、評分、合併
    items = patches.weekly_tools(items, set(rules.cfg.get('tool_weekly') or []), today)
    items = patches.finalize(items, rules, today, keep_days=SHOW_DAYS)
    items = patches.merge(items)
    items.sort(key=lambda x: (x['d'], x['rk']), reverse=True)

    # 4. 伺服器狀態（先抓，事故標題跟改版一起翻）
    stat = {}
    try:
        stat = collect_status(http, src_cfg['status'], t0, health)
    except Exception:  # noqa: BLE001
        errors.append('status: ' + traceback.format_exc()[-400:])
        traceback.print_exc()
    shorts = []
    for sv in stat.values():
        shorts += [a.get('t') for a in (sv.get('active') or [])] + [r.get('t') for r in (sv.get('recent') or [])]
        shorts += [c.get('n') for c in (sv.get('comps') or [])]

    # 5. 翻譯（重要的先翻；App 只顯示翻好的）
    tr_stats = {}
    try:
        from . import translate
        order = [x for x in items if x['s'] >= rules.cfg['show_min_score'] and
                 (today - dt.date.fromisoformat(x['d'])).days <= TRANSLATE_DAYS]
        order.sort(key=lambda x: -x['rk'])
        for x in items:
            if x.get('tool') and x.get('hl'):
                x['_tr_body'] = '重點：' + ' '.join(x['hl'])
        names = {s['id']: s['product'] + ' 更新紀錄' for s in src_cfg['patches']}
        tr_stats = translate.run(order, st, t0, names, shorts=shorts)
    except Exception:  # noqa: BLE001
        errors.append('translate: ' + traceback.format_exc()[-400:])
        traceback.print_exc()
    for x in items:
        x.pop('_tr_body', None)
        x.pop('_translate', None)
        x['b'] = (x.get('b') or '')[:420]
    short_map = tr_stats.pop('short_map', {}) if isinstance(tr_stats, dict) else {}
    for sv in stat.values():
        for a in (sv.get('active') or []) + (sv.get('recent') or []):
            if a.get('t') in short_map:
                a['tz'] = short_map[a['t']]
        for c in sv.get('comps') or []:
            if c.get('n') in short_map:
                c['nz'] = short_map[c['n']]

    # 6. 方案、匯率、方案頁變動、iOS App 版本
    plan_out = {}
    try:
        fx = plans.fx_rate(http, src_cfg['fx'], health) or st.load('fx.json', None)
        if fx:
            st.save('fx.json', fx)
        wstate, wevents = plans.watch(http, src_cfg['plan_pages'], st.load('plan_watch.json', {}), t0, health)
        st.save('plan_watch.json', wstate)
        apps = plans.app_versions(http, src_cfg['apps'], health)
        plan_out = plans.build(cfg('plans.json'), fx, wstate, apps, t0)
        health['plan_changes'] = len(wevents)
        for e in plans.recent_changes(wstate, t0):     # 方案頁變動留兩週（跟商城頁的提醒一樣久）
            vname = src_cfg['vendors'][e['v']]['name']
            t = f'{vname} 官方方案頁有變動'
            body = ('頁面上的價格數字變了：' + '、'.join(e['added'][:6])) if e['basis'] == 'prices' and e['added'] \
                else '官方方案頁上跟額度有關的文字有變動，方案表要重新核對。'
            items.insert(0, {'id': f"plan-{e['v']}-{e['at']}", 'src': 'plans', 'v': e['v'], 'p': '方案頁',
                             'd': e['at'][:10], 't': t, 'b': body, 'tz': t, 'sz': body, 'zh_native': True,
                             'url': e['url'], 'fx': 'tweak', 'tags': ['價格', '額度'], 's': 70, 'rk': 70,
                             'why': ['你訂閱的方案可能有變']})
    except Exception:  # noqa: BLE001
        errors.append('plans: ' + traceback.format_exc()[-400:])
        traceback.print_exc()

    # 7. 本機模型
    local_out = {}
    try:
        lc = cfg('local.json')
        cache = st.load('hf_cache.json.gz', {})
        llms = local.enrich_llms(http, lc['llm'], cache, t0, health, rig)
        ids = set()
        for m in lc['llm'] + lc.get('diffusion', []):
            ids |= {m.get('hf'), m.get('gguf'), *(m.get('hf_also') or [])}
        found = local.discover(http, ids, cache, t0, health, rig)
        tools = local.tool_versions(http, cache, t0, health)
        for x in items:
            if x['src'] in ('lmstudio', 'bionic') and x.get('app'):      # 新的排前面，第一個看到的就是最新版
                tools.setdefault('lmstudio' if x['app'] == 'LM Studio' else 'bionic',
                                 {'name': x['app'], 'ver': x.get('ver'), 'date': x['d'], 'url': x['url']})
            if x['src'] == 'nvidia' and 'nvidia' not in tools:
                tools['nvidia'] = {'name': 'NVIDIA 驅動', 'ver': x.get('ver'), 'date': x['d'], 'url': x['url']}
        st.save('hf_cache.json.gz', {k: v for k, v in cache.items()
                                      if (now() - (dt.datetime.fromisoformat(v['at'].replace('Z', '+00:00')))).days < 30})
        local_out = {'rig': rig, 'quants': lc['quants'], 'llm': llms, 'diffusion': lc.get('diffusion', []),
                     'found': found, 'tools': tools, 'stack': lc.get('stack'), 'cats': lc.get('cats')}
    except Exception:  # noqa: BLE001
        errors.append('local: ' + traceback.format_exc()[-400:])
        traceback.print_exc()

    # 8. 攻略保鮮檢查
    guide_out = {}
    try:
        local_ids = {m['id'] for m in local_out.get('llm', [])} | {m['id'] for m in local_out.get('diffusion', [])}
        guide_out = guide.evaluate(cfg('playbook.json'), models, local_ids, items, today)
    except Exception:  # noqa: BLE001
        errors.append('guide: ' + traceback.format_exc()[-400:])
        traceback.print_exc()

    # 9. 本週版本
    week = patches.week_code(today)
    monday = today - dt.timedelta(days=today.weekday())
    this_week = [x for x in items if x['d'] >= monday.isoformat() and x['s'] >= rules.cfg['show_min_score']]
    counts = {k: sum(1 for x in this_week if x['fx'] == k) for k in patches.FX_ZH}

    meta = {'generated': iso(t0), 'build': build_id, 'repo': 'PZWei0105/ai-meta', 'week': week,
            'week_start': monday.isoformat(), 'week_counts': counts, 'week_mine': sum(
                1 for x in this_week if x['s'] >= rules.cfg['mine_min_score']),
            'profile': {k: profile[k] for k in ('tiers', 'uses', 'tasks', 'name', 'paid') if k in profile},
            'vendors': src_cfg['vendors'], 'sources': {s['id']: {'p': s['product'], 'v': s['vendor'], 'url': s['url']}
                                                       for s in src_cfg['patches']},
            'health': health, 'translate': {k: tr_stats.get(k) for k in ('ok', 'model', 'done', 'cached', 'pending',
                                                                       'points', 'points_pending', 'short')},
            'rules': {'show_min': rules.cfg['show_min_score'], 'mine_min': rules.cfg['mine_min_score'],
                      'weights': rules.w}, 'errors': errors[:5]}
    outputs = {
        'meta.json': meta,
        'patches.json': {'generated': iso(t0), 'items': items, 'upcoming': upcoming},
        'prices.json': {'generated': iso(t0), 'models': models},
        'status.json': {'generated': iso(t0), 'vendors': stat, 'zh': short_map},
        'plans.json': dict(plan_out, generated=iso(t0)),
        'local.json': dict(local_out, generated=iso(t0)),
        'guide.json': dict(guide_out, generated=iso(t0)),
    }
    for name, obj in outputs.items():
        write_json(data_dir, name, obj)
        write_json(st.path / 'out', name, obj)
    runs = st.load('runs.json', [])
    runs.append({'at': iso(t0), 'secs': round((now() - t0).total_seconds(), 1), 'calls': http.calls,
                 'items': len(items), 'models': len(models), 'translate': tr_stats, 'errors': errors[:5]})
    st.save('runs.json', runs[-80:])
    st.save('health.json', health)
    diag = st.path / 'diag'
    diag.mkdir(exist_ok=True)
    for name in ('llm_setup.log', 'llama.log'):
        src = pathlib.Path('/tmp') / name
        if src.exists():
            (diag / name).write_text(src.read_text(encoding='utf-8', errors='replace')[-12000:], encoding='utf-8')
    print(f'[meta] items={len(items)} models={len(models)} calls={http.calls} '
          f'secs={(now() - t0).total_seconds():.1f} errors={len(errors)}', flush=True)
    return outputs


def run(mode: str) -> bool:
    from . import gitstate
    t0 = now()
    state_dir = gitstate.open_branch('state', '.state')
    st = State(state_dir)
    public = ROOT / 'public'
    build_id = copy_site(public)
    data_dir = public / 'data'
    if mode == 'deploy':
        for name in OUT_FILES:
            p = state_dir / 'out' / name
            if p.exists():
                data_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(p, data_dir / name)
        print('[meta] deploy only, build', build_id, flush=True)
        return True
    execute(Http(), st, t0, data_dir, build_id)
    gitstate.save_branch('state', '.state', 'state ' + iso(t0))
    return True
