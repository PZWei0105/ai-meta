"""離線測試用：依網址片段找 probe 抓下來的原始回應（probe-results 分支解開的資料夾）。"""
import json
import os
import pathlib
import re

DIRS = [pathlib.Path(p) / 'raw' for p in os.environ.get('PROBE', '').split(':') if p]


class R:
    def __init__(self, b, code=200):
        self.content = b
        self.status_code = code
        self.text = b.decode('utf-8', errors='replace')
        self.encoding = 'utf-8'

    def json(self):
        return json.loads(self.content.decode('utf-8-sig'))


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = 0
        self.log = []
        self.gh_token = ''

    DYNAMIC = [
        (re.compile(r'huggingface\.co/api/models/([^/?]+)/([^/?]+)/tree/main'), 'tree_{0}__{1}'),
        (re.compile(r'huggingface\.co/([^/?]+)/([^/?]+)/resolve/main/config\.json'), 'cfg_{0}__{1}'),
    ]

    def get(self, url, **kw):
        self.calls += 1
        self.log.append(url)
        names = [rx_name.format(*m.groups()) for rx, rx_name in self.DYNAMIC for m in [rx.search(url)] if m]
        names += [name for key, name in self.routes if key in url]
        for name in names:
            for d in DIRS:
                p = d / f'{name}.txt'
                if p.exists():
                    return R(p.read_bytes())
        return R(b'', 404)

    def text(self, url, **kw):
        r = self.get(url, **kw)
        if r.status_code != 200:
            raise RuntimeError(f'HTTP {r.status_code}')
        return r.text

    def json(self, url, **kw):
        r = self.get(url, **kw)
        if r.status_code != 200:
            raise RuntimeError(f'HTTP {r.status_code}')
        return r.json()
