"""跨輪資料：存在 repo 的 state 分支（每次只保留一個 commit）。"""
import gzip
import json
import pathlib


class State:
    def __init__(self, path: pathlib.Path):
        self.path = path

    def load(self, name, default):
        p = self.path / name
        if not p.exists():
            return default
        try:
            if name.endswith('.gz'):
                with gzip.open(p, 'rt', encoding='utf-8') as f:
                    return json.load(f)
            return json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return default

    def save(self, name, obj):
        p = self.path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        txt = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
        if name.endswith('.gz'):
            with gzip.open(p, 'wt', encoding='utf-8') as f:
                f.write(txt)
        else:
            p.write_text(txt, encoding='utf-8')


def write_json(folder: pathlib.Path, name: str, obj):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
