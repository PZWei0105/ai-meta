"""本機模型：精選清單（config/local.json）＋ Hugging Face 的實際檔案大小與架構 ＋ 新上架雷達。

精選清單由人工挑（附來源）；檔案大小、層數、注意力頭數這些數字每天從 Hugging Face 自動更新，不手抄。
"""
import re
import time

from . import vram
from .util import days_since, iso, now, parse_iso

HF = 'https://huggingface.co'
QUANT_RX = re.compile(r'(?:UD-)?(IQ\d_[A-Z]{1,3}|Q\d_K_XL|Q\d_K_[SML]|Q\d_K|Q\d_\d|Q8_0|MXFP4(?:_MOE)?|BF16|F16)', re.I)
GOOD_ORGS = {
    'qwen', 'google', 'meta-llama', 'mistralai', 'deepseek-ai', 'openai', 'microsoft', 'nvidia', 'zai-org', 'thudm',
    'moonshotai', 'minimaxai', 'liquidai', 'tencent', 'tencent-hunyuan', 'baidu', 'ibm-granite', 'allenai',
    'bytedance-seed', 'bytedance', 'xiaomimimo', 'inclusionai', 'stepfun-ai', 'black-forest-labs', 'wan-ai',
    'lightricks', 'stabilityai', 'hidream-ai', 'tongyi-mai', 'alibaba-pai', 'meituan-longcat', 'jetbrains',
    'huggingfacetb', 'cohereforai', 'coherelabs', 'ai21labs', 'kwaipilot', 'kwai-kolors', 'rednote-hilab',
    'apple', 'amazon', 'servicenow-ai', 'swiss-ai', 'upstage', 'lgai-exaone', 'naver-hyperclovax', 'skywork',
    'opengvlab', 'internlm', 'baai', 'ostris', 'comfy-org', 'genmo', 'thudm', 'zhipuai', 'facebook',
}
GGUF_ORGS = ('unsloth', 'bartowski', 'lmstudio-community', 'ggml-org')
BAD_WORDS = re.compile(r'uncensor|abliterat|nsfw|erotic|roleplay|humaniz|merge|lora|adapter|-gptq|-awq|-mlx|'
                       r'distill-test|test-|tiny-random|dummy', re.I)
TAG_KIND = {'text-generation': 'llm', 'image-text-to-text': 'llm', 'text-to-image': 'image', 'image-to-image': 'image',
            'text-to-video': 'video', 'image-to-video': 'video'}


def quant_sizes(tree: list) -> dict:
    """把 Hugging Face 檔案清單整理成 {壓縮等級: GiB}；分割檔加總。"""
    out = {}
    for f in tree or []:
        path = f.get('path') or ''
        if not path.lower().endswith('.gguf') or 'mmproj' in path.lower():
            continue
        size = (f.get('lfs') or {}).get('size') or f.get('size') or 0
        m = QUANT_RX.search(path.rsplit('/', 1)[-1]) or QUANT_RX.search(path)
        if not m or not size:
            continue
        q = m.group(1).upper()
        if 'UD-' in path.upper() and not q.endswith('_XL'):
            q = 'UD-' + q
        out[q] = out.get(q, 0) + size
    return {k: round(v / vram.GIB, 2) for k, v in out.items()}


def mmproj_size(tree: list):
    sizes = [((f.get('lfs') or {}).get('size') or f.get('size') or 0) for f in tree or []
             if 'mmproj' in (f.get('path') or '').lower() and (f.get('path') or '').lower().endswith('.gguf')]
    return round(min(sizes) / vram.GIB, 2) if sizes else None


def arch_from_config(cfg: dict) -> dict:
    """從 config.json 取出算對話記憶需要的數字。多模態模型的文字部分在 text_config。"""
    c = cfg.get('text_config') or cfg.get('llm_config') or cfg
    layers = c.get('num_hidden_layers') or c.get('n_layer') or c.get('num_layers')
    heads = c.get('num_attention_heads') or c.get('n_head')
    kv = c.get('num_key_value_heads') or c.get('num_kv_heads') or heads
    hidden = c.get('hidden_size') or c.get('d_model') or c.get('n_embd')
    head_dim = c.get('head_dim') or (hidden // heads if hidden and heads else None)
    out = {'layers': layers, 'kv_heads': kv, 'head_dim': head_dim, 'hidden': hidden}
    lt = c.get('layer_types')
    if isinstance(lt, list) and lt:
        full = sum(1 for x in lt if 'full' in str(x) or x == 'attention')
        swa = sum(1 for x in lt if 'sliding' in str(x))
        lin = sum(1 for x in lt if 'linear' in str(x) or 'mamba' in str(x) or 'delta' in str(x))
        out['kv_layers'] = full
        if swa:
            out['swa_layers'] = swa
            out['swa_window'] = c.get('sliding_window') or 4096
        if lin:
            out['state_gib'] = 0.15
    elif c.get('full_attention_interval') and layers:
        out['kv_layers'] = layers // int(c['full_attention_interval'])
        out['state_gib'] = 0.15
    elif c.get('sliding_window') and c.get('sliding_window_pattern') and layers:
        pat = int(c['sliding_window_pattern'])
        full = layers // pat
        out['kv_layers'] = full
        out['swa_layers'] = layers - full
        out['swa_window'] = c['sliding_window']
    if c.get('kv_lora_rank'):
        # MLA（DeepSeek 類）：每層只存壓縮後的向量
        out['kv_bpt'] = (layers or 0) * ((c.get('kv_lora_rank') or 512) + (c.get('qk_rope_head_dim') or 64)) * 2
    ne = c.get('num_experts') or c.get('n_routed_experts') or c.get('num_local_experts')
    if ne:
        out['experts'] = ne
        out['experts_active'] = c.get('num_experts_per_tok') or c.get('moe_topk') or c.get('num_experts_per_token')
    return {k: v for k, v in out.items() if v is not None}


def fetch_json_cached(http, cache: dict, key: str, url: str, t0, max_age_h: float, health: dict):
    c = cache.get(key)
    if c and days_since(c.get('at'), t0) * 24 < max_age_h:
        return c.get('data')
    try:
        data = http.json(url, bot=True, timeout=30)
        cache[key] = {'at': iso(t0), 'data': data}
        return data
    except Exception as e:  # noqa: BLE001
        health.setdefault('hf_errors', []).append(f'{key}: {type(e).__name__}: {e}'[:160])
        return c.get('data') if c else None


def enrich_llms(http, catalog: list, cache: dict, t0, health: dict, rig: dict):
    out = []
    for m in catalog:
        m = dict(m)
        if m.get('gguf'):
            tree = fetch_json_cached(http, cache, f"tree:{m['gguf']}", f"{HF}/api/models/{m['gguf']}/tree/main?recursive=true",
                                     t0, 24, health)
            if tree:
                qs = quant_sizes(tree)
                if qs:
                    m['quants'] = qs
                mp = mmproj_size(tree)
                if mp:
                    m['mmproj_gib'] = mp
        arch = {}
        if m.get('config_repo') or m.get('hf'):
            repo = m.get('config_repo') or m['hf']
            cfg = fetch_json_cached(http, cache, f"cfg:{repo}", f"{HF}/{repo}/resolve/main/config.json", t0, 24 * 7, health)
            if isinstance(cfg, dict):
                arch = arch_from_config(cfg)
        arch.update(m.get('arch') or {})        # 人工覆寫優先
        m['arch'] = arch
        if not m.get('quants') and m.get('total_b'):
            m['quants'] = {'Q4_K_M': round(vram.guess_weights_gib(m['total_b'], 4.85), 2),
                           'Q8_0': round(vram.guess_weights_gib(m['total_b'], 8.5), 2)}
            m['quants_guess'] = True
        spec = dict(arch, total_b=m.get('total_b'), active_b=m.get('active_b'))
        pick = m.get('pick') or ('Q4_K_M' if 'Q4_K_M' in (m.get('quants') or {}) else None)
        if pick and pick in (m.get('quants') or {}):
            w = m['quants'][pick] + (m.get('mmproj_gib') or 0 if 'vision' in (m.get('cats') or []) else 0)
            m['fit'] = vram.plan(spec, w, m.get('ctx_default') or 32768, rig)
            m['fit']['q'] = pick
        out.append(m)
    return out


def discover(http, catalog_ids: set, cache: dict, t0, health: dict, rig: dict, limit=14):
    """Hugging Face 熱門新模型：只收知名官方團隊、60 天內發布、不在精選清單裡的。"""
    seen, cands = set(), []
    for tag, kind in TAG_KIND.items():
        url = (f'{HF}/api/models?pipeline_tag={tag}&sort=trendingScore&limit=40'
               '&expand[]=safetensors&expand[]=gguf&expand[]=createdAt&expand[]=downloads&expand[]=likes'
               '&expand[]=trendingScore&expand[]=cardData&expand[]=pipeline_tag')
        data = fetch_json_cached(http, cache, f'trend:{tag}', url, t0, 6, health) or []
        for m in data:
            mid = m.get('id') or ''
            org = mid.split('/')[0].lower()
            if mid in seen or mid in catalog_ids or org not in GOOD_ORGS or BAD_WORDS.search(mid):
                continue
            if days_since(m.get('createdAt'), t0) > 60:
                continue
            params = ((m.get('safetensors') or {}).get('total') or (m.get('gguf') or {}).get('total') or 0) / 1e9
            if params < 0.5:
                continue
            seen.add(mid)
            card = m.get('cardData') or {}
            cands.append({'id': mid, 'kind': kind, 'tag': tag, 'params_b': round(params, 1),
                          'created': (m.get('createdAt') or '')[:10], 'likes': m.get('likes'),
                          'downloads': m.get('downloads'), 'trend': round(m.get('trendingScore') or 0),
                          'license': card.get('license'), 'url': f'{HF}/{mid}'})
    cands.sort(key=lambda x: -(x['trend'] or 0))
    cands = cands[:limit]
    for c in cands:
        name = c['id'].split('/')[-1]
        if c['kind'] == 'llm':
            res = fetch_json_cached(http, cache, f'ggufsearch:{name}',
                                    f'{HF}/api/models?search={name}-GGUF&limit=20&expand[]=downloads', t0, 12, health) or []
            hits = [r['id'] for r in res if r.get('id', '').split('/')[0].lower() in GGUF_ORGS]
            c['gguf'] = hits[0] if hits else None
            cfg = fetch_json_cached(http, cache, f"cfg:{c['id']}", f"{HF}/{c['id']}/resolve/main/config.json", t0,
                                    24 * 7, health)
            arch = arch_from_config(cfg) if isinstance(cfg, dict) else {}
            active = None
            if arch.get('experts') and arch.get('experts_active'):
                # 粗估活躍參數：專家只用 k/n，其餘（注意力、嵌入）約占 8%
                active = round(c['params_b'] * (0.08 + 0.92 * arch['experts_active'] / arch['experts']), 1)
            c['active_b'] = active
            w = vram.guess_weights_gib(c['params_b'], 4.85)
            spec = dict(arch, total_b=c['params_b'], active_b=active)
            if not arch.get('layers'):
                spec.update(layers=48, kv_heads=8, head_dim=128)
            c['fit'] = vram.plan(spec, w, 32768, rig)
            c['fit']['q'] = 'Q4_K_M（估）'
        else:
            # 生圖／生影片：用 fp8 估本體大小（每十億參數約 1 GB），文字編碼器另計
            w = c['params_b'] * 1e9 / vram.GIB
            c['fit'] = {'need': round(w + 2.5, 1), 'weights': round(w, 1), 'usable': rig['vram_gib'] - rig['vram_reserve_gib']}
            usable = c['fit']['usable']
            need = c['fit']['need']
            c['fit']['level'] = 'easy' if need <= usable * 0.85 else 'tight' if need <= usable else \
                'offload' if need <= usable + 30 else 'no'
            c['fit']['q'] = 'fp8（估）'
    return cands


def tool_versions(http, cache, t0, health):
    out = {}
    for key, repo, name in (('ollama', 'ollama/ollama', 'Ollama'), ('comfyui', 'comfyanonymous/ComfyUI', 'ComfyUI'),
                            ('llamacpp', 'ggml-org/llama.cpp', 'llama.cpp')):
        data = fetch_json_cached(http, cache, f'latest:{repo}', f'https://api.github.com/repos/{repo}/releases/latest',
                                 t0, 3, health)
        if isinstance(data, dict) and data.get('tag_name'):
            out[key] = {'name': name, 'ver': re.sub(r'^v', '', data['tag_name']),
                        'date': (data.get('published_at') or '')[:10], 'url': data.get('html_url')}
    return out


__all__ = ['quant_sizes', 'arch_from_config', 'enrich_llms', 'discover', 'tool_versions', 'now', 'time', 'parse_iso']
