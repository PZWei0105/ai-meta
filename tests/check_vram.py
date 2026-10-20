"""確認 App（site/app.js）和管線（pipeline/vram.py）算出來的「跑得動嗎」一模一樣。

App 裡拉對話長度、換壓縮等級時是在手機上即時重算的；兩邊公式要同步，改一邊就跑這個檢查：
    python3 tests/check_vram.py [local.json]
沒給 local.json 時用內建的幾組架構。需要 node。
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import vram  # noqa: E402

BUILTIN = [
    ({'layers': 64, 'kv_heads': 4, 'head_dim': 256, 'hidden': 5120, 'kv_layers': 16, 'state_gib': 0.161, 'total_b': 27.8}, 16.19),
    ({'layers': 40, 'kv_heads': 2, 'head_dim': 256, 'hidden': 2048, 'kv_layers': 10, 'state_gib': 0.079, 'total_b': 36.0,
      'active_b': 3.0}, 20.3),
    ({'layers': 60, 'kv_heads': 16, 'head_dim': 256, 'hidden': 5376, 'kv_layers': 10, 'swa_layers': 50, 'swa_window': 1024,
      'kv_bpt': 81920, 'total_b': 31.3}, 17.32),
    ({'layers': 36, 'kv_heads': 8, 'head_dim': 64, 'hidden': 2880, 'kv_layers': 18, 'swa_layers': 18, 'swa_window': 128,
      'total_b': 116.8, 'active_b': 5.1}, 60.88),
]


def cases_from(local_json):
    data = json.loads(pathlib.Path(local_json).read_text(encoding='utf-8'))
    out = []
    for m in data.get('llm', []):
        f = m.get('fit')
        if not f:
            continue
        spec = dict(m.get('arch') or {}, total_b=m.get('total_b'), active_b=m.get('active_b'))
        out.append((spec, f['weights']))
    return out


def js_results(cases, ctxs, kvqs):
    src = (ROOT / 'site' / 'app.js').read_text(encoding='utf-8')
    start = src.index('const GIB = 1024 ** 3;')
    end = src.index('function speedWord')
    block = src[start:end]
    script = f"""
const S = {{ d: {{ local: {{ rig: {json.dumps(vram.DEFAULT_RIG)} }} }} }};
{block}
const cases = {json.dumps([[c[0], c[1]] for c in cases])};
const out = [];
for (const [m, w] of cases) for (const ctx of {json.dumps(ctxs)}) for (const kvq of {json.dumps(kvqs)}) {{
  const p = vramPlan(m, w, ctx, kvq);
  out.push({{ need: p.need, kv: p.kv, level: p.level, tps: p.tps }});
}}
console.log(JSON.stringify(out));
"""
    r = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def main():
    cases = cases_from(sys.argv[1]) if len(sys.argv) > 1 else BUILTIN
    ctxs, kvqs = [4096, 32768, 131072], ['f16', 'q8_0']
    js = js_results(cases, ctxs, kvqs)
    bad, i = 0, 0
    for m, w in cases:
        for ctx in ctxs:
            for kvq in kvqs:
                py = vram.plan(m, w, ctx, vram.DEFAULT_RIG, kvq)
                j = js[i]
                i += 1
                same = (abs(py['need'] - j['need']) < 0.02 and abs(py['kv'] - j['kv']) < 0.02 and py['level'] == j['level']
                        and abs(py['tps'] - j['tps']) <= max(0.2, py['tps'] * 0.005))
                if not same:
                    bad += 1
                    print('不一致', m.get('total_b'), w, ctx, kvq, 'py', py['need'], py['level'], py['tps'],
                          'js', round(j['need'], 2), j['level'], j['tps'])
    print(f'{i} 組比對，{bad} 組不一致')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
