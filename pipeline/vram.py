"""本機模型「跑得動嗎」的估算：吃多少顯示記憶體（VRAM）、多快。

site/app.js 的 vramPlan()／speedOf() 是同一套算法（App 裡拉對話長度、換壓縮等級時即時重算）。
改這裡就要改那裡，tests/check_vram.py 會用同一組案例比對兩邊結果。

單位一律是 GiB（1024³ bytes）。Hugging Face 顯示的檔案大小是 bytes，進來就換算。
"""
import math

GIB = 1024 ** 3

# 預設硬體（config/profile.json 會覆蓋）
DEFAULT_RIG = {
    'vram_gib': 24.0,          # RTX 5090 Laptop GPU
    'vram_reserve_gib': 1.0,   # Windows 桌面、瀏覽器、驅動自己用掉的
    'gpu_bw_gbs': 896.0,       # GDDR7 256-bit 28Gbps
    'ram_gib': 64.0,
    'ram_reserve_gib': 18.0,   # Windows 與開著的程式
    'ram_bw_gbs': 89.6,        # DDR5-5600 雙通道（理論值）
}

KV_BYTES = {'f16': 2.0, 'q8_0': 34 / 32, 'q4_0': 18 / 32}
RUNTIME_GIB = 0.35            # CUDA 與推論程式本身
SWA_PAD = 512                 # 滑動視窗層實際會多留一批（llama.cpp 的 ubatch）
# 實際能用到的頻寬比例＋每個 token 的固定開銷，用公開實測校準：
#   密集模型：Muse Glimmer 官方在桌機 RTX 5090 量到 74.9 token/秒（約 17 GB 檔）；32B Q4 在 4090 約 35–40
#   MoE：Qwen3-30B-A3B Q4 在 4090 約 150–170（專家分散讀取，頻寬用不滿）
EFF_GPU_DENSE = 0.72
EFF_GPU_MOE = 0.40
EFF_CPU = 0.55
T_FIXED = 0.001               # 秒／token：排程、同步這些跟模型大小無關的時間
MAX_TPS = 260

LEVELS = ('easy', 'tight', 'offload', 'no')


def kv_bytes_per_token(m: dict, kvq: str = 'f16') -> float:
    """每個 token 的對話記憶大小（bytes），不含滑動視窗層。"""
    if m.get('kv_bpt'):                       # 特殊架構（MLA 等）直接給值（以 f16 計）
        return float(m['kv_bpt']) * KV_BYTES[kvq] / 2.0
    layers = m.get('kv_layers') or m.get('layers') or 0
    return 2.0 * layers * (m.get('kv_heads') or 0) * (m.get('head_dim') or 0) * KV_BYTES[kvq]


def kv_gib(m: dict, ctx: int, kvq: str = 'f16') -> float:
    full = kv_bytes_per_token(m, kvq) * ctx
    swa = 0.0
    if m.get('swa_layers') and m.get('swa_window'):
        per = 2.0 * m['swa_layers'] * (m.get('kv_heads') or 0) * (m.get('head_dim') or 0) * KV_BYTES[kvq]
        swa = per * min(ctx, int(m['swa_window']) + SWA_PAD)
    return (full + swa) / GIB + float(m.get('state_gib') or 0)


def compute_gib(m: dict, ctx: int) -> float:
    """推論暫存（llama.cpp 開 Flash Attention 的大約值）。"""
    width = (m.get('hidden') or 4096) / 4096
    return 0.30 + 0.25 * width + ctx * 6e-6 * width


def plan(m: dict, weights_gib: float, ctx: int, rig: dict | None = None, kvq: str = 'f16') -> dict:
    """回傳記憶體分配與判定。m 是模型規格（layers、kv_heads、head_dim、total_b、active_b…）。"""
    rig = dict(DEFAULT_RIG, **(rig or {}))
    usable = rig['vram_gib'] - rig['vram_reserve_gib']
    ram_budget = max(0.0, rig['ram_gib'] - rig['ram_reserve_gib'])
    kv = kv_gib(m, ctx, kvq)
    comp = compute_gib(m, ctx)
    need = weights_gib + kv + comp + RUNTIME_GIB
    moe = bool(m.get('active_b')) and (m.get('active_b') or 0) < (m.get('total_b') or 0) * 0.6
    on_gpu_w = weights_gib
    spill = max(0.0, need - usable)
    if spill > 0:
        on_gpu_w = max(0.0, weights_gib - spill)
    if need <= usable * 0.85:
        level = 'easy'
    elif need <= usable:
        level = 'tight'
    elif spill <= ram_budget and on_gpu_w >= 0:
        level = 'offload'
    else:
        level = 'no'
    if level == 'offload' and kv + comp + RUNTIME_GIB > usable:
        level = 'no'   # 連對話記憶都放不進顯卡，實際上不可行
    out = {
        'level': level, 'need': round(need, 2), 'usable': round(usable, 2),
        'weights': round(weights_gib, 2), 'kv': round(kv, 2), 'compute': round(comp + RUNTIME_GIB, 2),
        'spill': round(spill, 2), 'moe': moe,
    }
    out['tps'] = speed(m, weights_gib, spill, ctx, rig, kvq, moe)
    return out


def speed(m: dict, weights_gib: float, spill_gib: float, ctx: int, rig: dict, kvq: str, moe: bool) -> float:
    """每秒產生幾個 token（估算）。記憶體頻寬決定上限：每產生一個 token 要把用到的權重讀一遍。"""
    gbw = rig['gpu_bw_gbs'] * 1e9 / GIB
    cbw = rig['ram_bw_gbs'] * 1e9 / GIB
    used_ctx = min(ctx, 4096)                               # 一般對話時，記憶裡大約有幾千 token
    kv_read = kv_bytes_per_token(m, kvq) * used_ctx / GIB
    if moe:
        frac = (m.get('active_b') or 1) / max(1e-6, m.get('total_b') or 1)
        per_tok = weights_gib * frac
        eff = EFF_GPU_MOE
    else:
        frac = 1.0
        per_tok = weights_gib
        eff = EFF_GPU_DENSE
    if spill_gib <= 0:
        t = (per_tok + kv_read) / (gbw * eff)
    else:
        cpu_share = min(1.0, spill_gib / max(1e-6, weights_gib))
        if moe:
            # 專家層放到系統記憶體：每個 token 只讀被選中的專家
            t = (per_tok * (1 - cpu_share) + kv_read) / (gbw * eff) + per_tok * cpu_share / (cbw * EFF_CPU)
        else:
            t = (weights_gib * (1 - cpu_share) + kv_read) / (gbw * eff) + weights_gib * cpu_share / (cbw * EFF_CPU)
    t += T_FIXED
    tps = 1.0 / t if t > 0 else MAX_TPS
    return round(min(MAX_TPS, tps), 1)


def guess_weights_gib(params_b: float, bits: float) -> float:
    """沒有實際檔案時，用參數量粗估檔案大小（多 3% 給中繼資料與嵌入層）。"""
    return params_b * 1e9 * bits / 8 / GIB * 1.03


def ctx_to_chars(ctx: int) -> int:
    """對話長度大約等於幾個中文字（現代分詞器平均 1 token ≈ 1.3 字）。"""
    return int(math.floor(ctx * 1.3 / 1000) * 1000)
