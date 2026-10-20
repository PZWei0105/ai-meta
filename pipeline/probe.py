"""開發用：實際抓一輪候選資料來源，把原始回應與重要標頭存到 probe-results 分支供檢查。"""
import datetime as dt
import json
import os
import pathlib
import platform
import shutil
import time

import requests

from . import gitstate
from .util import UA_BOT, UA_BROWSER

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_MAX = 4_000_000
KEEP_HEADERS = ('content-type', 'access-control-allow-origin', 'cache-control', 'etag', 'last-modified',
                'retry-after', 'x-ratelimit-remaining', 'server', 'location', 'vary')


def run():
    targets = json.loads((ROOT / 'control' / 'probe.json').read_text(encoding='utf-8'))
    out = gitstate.open_branch('probe-results', '.probe')
    for p in list(out.iterdir()):
        if p.name != '.git':
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    (out / 'raw').mkdir(exist_ok=True)

    session = requests.Session()
    token = os.environ.get('GH_TOKEN', '')
    summary = {'started': dt.datetime.now(dt.timezone.utc).isoformat(),
               'python': platform.python_version(), 'results': []}

    for t in targets:
        name = t['name']
        meta = {'name': name, 'url': t['url']}
        headers = {'User-Agent': UA_BOT if t.get('bot_ua') else UA_BROWSER,
                   'Accept': t.get('accept', '*/*'), 'Accept-Language': 'en-US,en;q=0.9,zh-TW;q=0.8',
                   'Origin': 'https://pzwei0105.github.io'}
        if t['url'].startswith('https://api.github.com/') and token:
            headers['Authorization'] = f'Bearer {token}'
        headers.update(t.get('headers') or {})
        t0 = time.time()
        try:
            r = session.get(t['url'], headers=headers, timeout=t.get('timeout', 40),
                            allow_redirects=t.get('redirects', True))
            raw = r.content
            meta.update(status=r.status_code, final_url=r.url, size=len(raw),
                        headers={k: r.headers.get(k) for k in KEEP_HEADERS if r.headers.get(k)},
                        history=[h.status_code for h in r.history])
            (out / 'raw' / f'{name}.txt').write_bytes(raw[:t.get('max', DEFAULT_MAX)])
        except Exception as e:  # noqa: BLE001 — 開發探測，記錄所有錯誤
            meta['error'] = repr(e)[:500]
        meta['elapsed'] = round(time.time() - t0, 2)
        summary['results'].append(meta)
        print(json.dumps(meta, ensure_ascii=False)[:300], flush=True)
        time.sleep(t.get('sleep', 1.0))

    summary['finished'] = dt.datetime.now(dt.timezone.utc).isoformat()
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                      encoding='utf-8')
    gitstate.save_branch('probe-results', '.probe', 'probe ' + summary['finished'])
