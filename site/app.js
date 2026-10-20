/* 版本答案 META — PZ 的 AI 版本答案。純 HTML／CSS／JS，資料由 GitHub Actions 每小時更新。 */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const S = { d: {}, view: 'home', pm: 'mine', pv: 'all', open: new Set(), shopV: 'claude', lcat: 'chat', live: {}, scanning: false };
const VNAME = { claude: 'Claude', chatgpt: 'ChatGPT', gemini: 'Gemini', grok: 'Grok', local: '本機' };
const FX = {
  buff: ['▲', '加強'], nerf: ['▼', '削弱'], new: ['＋', '新增'], gone: ['✕', '移除'], tweak: ['◆', '調整'], fix: ['●', '修正'],
};
const LV = { easy: '輕鬆跑', tight: '跑得動，但吃緊', offload: '要借系統記憶體', no: '跑不動' };
const LV_SHORT = { easy: '輕鬆跑', tight: '吃緊', offload: '借記憶體', no: '跑不動' };
const ST = { ok: '正常', minor: '小狀況', major: '部分故障', critical: '大當機', unknown: '讀不到' };
const ICON = {
  close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
};
const TASK_ICON = { code: '⌨', novel: '✎', script: '▤', research: '⌕', translate: '文', image: '▣', video: '▶', trend: '↗' };

// ------------------------------------------------------------------ 共用格式
const pad = (n) => String(n).padStart(2, '0');
const WD = '日一二三四五六';
function twDate(iso) { const d = new Date(iso + (iso.length === 10 ? 'T12:00:00+08:00' : '')); return d; }
function md(iso) { if (!iso) return ''; const d = twDate(iso); return `${d.getMonth() + 1}/${d.getDate()}`; }
function mdw(iso) { const d = twDate(iso); return `${d.getMonth() + 1}/${d.getDate()}（${WD[d.getDay()]}）`; }
function hm(iso) { const d = new Date(iso); return `${md(iso)} ${pad(d.getHours())}:${pad(d.getMinutes())}`; }
function ago(iso) {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return '剛剛';
  if (m < 60) return `${m} 分鐘前`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} 小時前`;
  return `${Math.round(h / 24)} 天前`;
}
function dayDiff(iso) {
  const a = new Date(); a.setHours(12, 0, 0, 0);
  return Math.round((twDate(iso).getTime() - a.getTime()) / 86400000);
}
function relDay(iso) {
  const n = -dayDiff(iso);
  if (n <= 0) return '今天';
  if (n === 1) return '昨天';
  if (n < 7) return `${n} 天前`;
  return md(iso);
}
const usd = (x) => (x == null ? '—' : `$${x >= 100 ? Math.round(x) : x >= 1 ? +x.toFixed(2) : +x.toFixed(3)}`);
const twd = (x) => (x == null ? '—' : `NT$${Math.round(x).toLocaleString('en-US')}`);
const rate = () => S.d.plans?.fx?.usd_twd || null;
const toTwd = (u) => (rate() && u != null ? u * rate() : null);
function ctxLabel(n) { if (n >= 1e6) return `${+(n / 1e6).toFixed(1)}M`; return `${Math.round(n / 1024)}K`; }
function ctxChars(n) { const c = Math.round(n * 1.3 / 1000) * 1000; return c >= 10000 ? `約 ${+(c / 10000).toFixed(1)} 萬字` : `約 ${c.toLocaleString()} 字`; }
function vd(v, label) { return `<span class="vd vc-${esc(v)}">${esc(label || VNAME[v] || v)}</span>`; }
function fxChip(fx) { const f = FX[fx] || FX.tweak; return `<span class="fx fx-${esc(fx)}"><i>${f[0]}</i>${f[1]}</span>`; }

// ------------------------------------------------------------------ 設定（只存在這台裝置）
const PREF_KEY = 'meta.prefs.v1';
const KEY_KEY = 'meta.key.v1';
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* 私密瀏覽 */ } }
function defaults() {
  const p = S.d.meta?.profile || {};
  return { v: 1, tiers: { ...(p.tiers || {}) }, hits: {}, uses: JSON.parse(JSON.stringify(p.uses || {})), ctx: 32768, kvq: 'f16', theme: 'auto', budget: null, quant: {} };
}
function prefs() {
  if (S.prefs) return S.prefs;
  let saved = null;
  try { saved = JSON.parse(lsGet(PREF_KEY) || 'null'); } catch (e) { saved = null; }
  const d = defaults();
  S.prefs = saved ? { ...d, ...saved, tiers: { ...d.tiers, ...(saved.tiers || {}) }, uses: { ...d.uses, ...(saved.uses || {}) }, hits: { ...(saved.hits || {}) }, quant: { ...(saved.quant || {}) } } : d;
  return S.prefs;
}
function savePrefs() { lsSet(PREF_KEY, JSON.stringify(S.prefs)); }
function applyTheme() { const t = prefs().theme; if (t === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', t); }

// ------------------------------------------------------------------ 讀資料
const FILES = ['meta', 'patches', 'prices', 'status', 'plans', 'local', 'guide'];
async function loadData(force) {
  const q = force ? `?t=${Date.now()}` : '';
  const res = await Promise.all(FILES.map((n) => fetch(`data/${n}.json${q}`, { cache: force ? 'no-store' : 'no-cache' })
    .then((r) => (r.ok ? r.json() : null)).catch(() => null)));
  const before = S.d.meta?.generated;
  FILES.forEach((n, i) => { if (res[i]) S.d[n] = res[i]; });
  if (!S.d.meta) throw new Error('讀不到資料，請確認網路後再按一次「更新」。');
  return before !== S.d.meta.generated;
}

// ------------------------------------------------------------------ 跑得動嗎（和 pipeline/vram.py 同一套算法）
const GIB = 1024 ** 3;
const KVB = { f16: 2, q8_0: 34 / 32, q4_0: 18 / 32 };
const RUNTIME_GIB = 0.35, EFF_DENSE = 0.70, EFF_MOE = 0.48, EFF_CPU = 0.55, MAX_TPS = 260;
function kvBpt(m, kvq) {
  if (m.kv_bpt) return m.kv_bpt * KVB[kvq] / 2;
  const layers = m.kv_layers ?? m.layers ?? 0;
  return 2 * layers * (m.kv_heads || 0) * (m.head_dim || 0) * KVB[kvq];
}
function kvGib(m, ctx, kvq) {
  let full = kvBpt(m, kvq) * ctx;
  let swa = 0;
  if (m.swa_layers && m.swa_window) swa = 2 * m.swa_layers * (m.kv_heads || 0) * (m.head_dim || 0) * KVB[kvq] * Math.min(ctx, m.swa_window);
  return (full + swa) / GIB + (m.state_gib || 0);
}
function computeGib(m, ctx) { const w = (m.hidden || 4096) / 4096; return 0.30 + 0.25 * w + ctx * 6e-6 * w; }
function rig() { return S.d.local?.rig || { vram_gib: 24, vram_reserve_gib: 1, gpu_bw_gbs: 896, ram_gib: 64, ram_reserve_gib: 18, ram_bw_gbs: 89.6 }; }
function vramPlan(m, wGib, ctx, kvq) {
  const r = rig();
  const usable = r.vram_gib - r.vram_reserve_gib;
  const ramBudget = Math.max(0, r.ram_gib - r.ram_reserve_gib);
  const kv = kvGib(m, ctx, kvq);
  const comp = computeGib(m, ctx);
  const need = wGib + kv + comp + RUNTIME_GIB;
  const moe = !!m.active_b && m.active_b < (m.total_b || 0) * 0.6;
  const spill = Math.max(0, need - usable);
  let level = need <= usable * 0.85 ? 'easy' : need <= usable ? 'tight' : spill <= ramBudget ? 'offload' : 'no';
  if (level === 'offload' && kv + comp + RUNTIME_GIB > usable) level = 'no';
  return { level, need, usable, weights: wGib, kv, compute: comp + RUNTIME_GIB, spill, moe, tps: speedOf(m, wGib, spill, ctx, r, kvq, moe) };
}
function speedOf(m, wGib, spill, ctx, r, kvq, moe) {
  const gbw = r.gpu_bw_gbs * 1e9 / GIB, cbw = r.ram_bw_gbs * 1e9 / GIB;
  const kvRead = kvBpt(m, kvq) * Math.min(ctx, 4096) / GIB;
  const frac = moe ? (m.active_b || 1) / Math.max(1e-6, m.total_b || 1) : 1;
  const per = wGib * frac;
  const eff = moe ? EFF_MOE : EFF_DENSE;
  let t;
  if (spill <= 0) t = (per + kvRead) / (gbw * eff);
  else {
    const share = Math.min(1, spill / Math.max(1e-6, wGib));
    t = moe ? (per * (1 - share) + kvRead) / (gbw * eff) + per * share / (cbw * EFF_CPU)
      : (wGib * (1 - share) + kvRead) / (gbw * eff) + wGib * share / (cbw * EFF_CPU);
  }
  return Math.round(Math.min(MAX_TPS, t > 0 ? 1 / t : MAX_TPS) * 10) / 10;
}
function speedWord(tps) { return tps >= 60 ? '飛快' : tps >= 25 ? '順暢' : tps >= 10 ? '可以用' : tps >= 4 ? '會等' : '很慢'; }
function specOf(m) { return { ...(m.arch || {}), total_b: m.total_b, active_b: m.active_b }; }
function pickQuant(m) {
  const qs = m.quants || {};
  const saved = prefs().quant[m.id];
  if (saved && qs[saved] != null) return saved;
  if (m.pick && qs[m.pick] != null) return m.pick;
  for (const q of ['Q4_K_M', 'UD-Q4_K_XL', 'Q4_K_XL', 'MXFP4', 'Q4_K_S', 'Q5_K_M', 'Q8_0']) if (qs[q] != null) return q;
  return Object.keys(qs)[0];
}
function llmFit(m, q) {
  q = q || pickQuant(m);
  const w = (m.quants || {})[q];
  if (w == null) return null;
  const wv = w + ((m.cats || []).includes('vision') && m.mmproj_gib ? m.mmproj_gib : 0);
  const p = prefs();
  const ctx = Math.min(p.ctx, m.ctx_max || p.ctx);
  return { ...vramPlan(specOf(m), wv, ctx, p.kvq), q, ctx };
}
function diffFit(m, vi) {
  const r = rig();
  const usable = r.vram_gib - r.vram_reserve_gib;
  const v = (m.variants || [])[vi ?? (m.rec ?? 0)] || (m.variants || [])[0];
  if (!v) return null;
  const te = Math.max(0, ...(m.encoders || []).map((e) => e.gib || 0));
  const act = m.act_gib || 2;
  const vae = m.vae_gib || 0.3;
  const need = Math.max(v.gib + act + vae + RUNTIME_GIB, te + 1);
  const level = need <= usable * 0.85 ? 'easy' : need <= usable ? 'tight' : need - usable <= r.ram_gib - r.ram_reserve_gib ? 'offload' : 'no';
  return { level, need, usable, weights: v.gib, kv: act, compute: vae + RUNTIME_GIB, spill: Math.max(0, need - usable), variant: v, te };
}
function vbar(f, big) {
  if (!f) return '';
  const r = rig();
  const total = Math.max(r.vram_gib, f.need + 0.5);
  const pct = (x) => `${Math.max(0, x) / total * 100}%`;
  const onGpu = Math.min(f.weights, Math.max(0, f.weights - f.spill));
  const spillW = Math.min(f.spill, f.weights);
  return `<div class="vbar${big ? ' big' : ''}" role="img" aria-label="需要 ${f.need.toFixed(1)} GB，顯示卡可用 ${f.usable.toFixed(0)} GB">
    <i class="w" style="width:${pct(onGpu)}"></i><i class="k" style="width:${pct(f.kv)}"></i><i class="c" style="width:${pct(f.compute)}"></i>${spillW > 0 ? `<i class="s" style="width:${pct(spillW)}"></i>` : ''}
    <span class="cap" style="left:${pct(f.usable)}"></span></div>`;
}

// ------------------------------------------------------------------ 訂閱方針（固定規則）
const HITS = { unknown: '還沒填', never: '幾乎不會撞到', monthly: '偶爾（一個月幾次）', weekly: '常常（每週都會）', daily: '幾乎每天' };
function planOf(v, id) { return (S.d.plans?.vendors?.[v]?.plans || []).find((p) => p.id === id); }
function subVerdict(v) {
  const PL = S.d.plans?.vendors?.[v];
  if (!PL) return null;
  const p = prefs();
  const tier = p.tiers[v] || 'free';
  const order = PL.plans.map((x) => x.id);
  const cur = planOf(v, tier) || PL.plans[0];
  const idx = order.indexOf(cur.id);
  const uses = p.uses[v] || [];
  const hit = p.hits[v] || 'unknown';
  const tasks = S.d.plans?.tasks || {};
  const reasons = [];
  const paidOthers = Object.keys(S.d.plans.vendors).filter((x) => x !== v && (planOf(x, p.tiers[x])?.usd || 0) > 0);
  if (!cur.usd) {
    const myTasks = new Set(Object.values(p.uses).flat());
    const gaps = [...myTasks].filter((t) => !paidOthers.some((x) => planOf(x, p.tiers[x])?.covers?.[t]));
    const next = PL.plans.find((x) => x.usd > 0 && gaps.some((t) => x.covers?.[t]));
    if (next) {
      const ts = gaps.filter((t) => next.covers?.[t]);
      reasons.push(`你目前付費的方案都沒有「${ts.map((t) => tasks[t] || t).join('、')}」，${PL.name} ${next.name} 有：${ts.map((t) => next.covers[t]).join('；')}`);
      return { v, kind: 'try', label: `值得試 ${next.name}`, cur, reasons, delta: next.usd };
    }
    reasons.push('免費版就好：你需要的功能，付費的方案都已經涵蓋了。');
    return { v, kind: 'keep', label: '維持免費', cur, reasons };
  }
  if (!uses.length) {
    reasons.push(`每月約 ${twd(toTwd(cur.usd))}，但還沒告訴我你拿它做什麼；到下面勾選用途，才能判斷值不值得。`);
    return { v, kind: 'ask', label: '先填用途', cur, reasons };
  }
  const higher = PL.plans[idx + 1];
  const lowerPaid = [...PL.plans.slice(0, idx)].reverse().find((x) => x.usd > 0);
  if ((hit === 'daily' || hit === 'weekly') && higher) {
    reasons.push(`你${HITS[hit]}撞到額度。升到 ${higher.name} 每月多 ${usd(higher.usd - cur.usd)}（約 ${twd(toTwd(higher.usd - cur.usd))}）。`);
    if (higher.lift) reasons.push(higher.lift);
    reasons.push('先試試「攻略」裡的省額度做法，還是常撞再升。');
    return { v, kind: 'up', label: `可考慮升 ${higher.name}`, cur, reasons, delta: higher.usd - cur.usd };
  }
  if ((hit === 'daily' || hit === 'weekly') && !higher) {
    reasons.push('已經是最高方案還常撞額度：把翻譯、摘要這類大量雜事分給本機模型或另一家，主力額度留給寫程式與長篇。');
    return { v, kind: 'keep', label: '維持，改分流', cur, reasons };
  }
  if (hit === 'never' && lowerPaid) {
    const lose = (cur.gets || []).filter((g) => !(lowerPaid.gets || []).includes(g)).slice(0, 4);
    reasons.push(`幾乎不會撞到額度，降到 ${lowerPaid.name} 每月省 ${usd(cur.usd - lowerPaid.usd)}（約 ${twd(toTwd(cur.usd - lowerPaid.usd))}）。`);
    if (lose.length) reasons.push(`會少掉：${lose.join('；')}。這些你用得到就維持。`);
    return { v, kind: 'down', label: `可考慮降 ${lowerPaid.name}`, cur, reasons, delta: lowerPaid.usd - cur.usd };
  }
  const uniq = uses.filter((t) => !paidOthers.some((x) => planOf(x, p.tiers[x])?.covers?.[t]));
  if (!uniq.length && paidOthers.length) {
    reasons.push(`你勾的用途（${uses.map((t) => tasks[t] || t).join('、')}）其他付費方案都做得到。`);
    reasons.push(`如果沒有非它不可的理由，每月可省 ${twd(toTwd(cur.usd))}。`);
    return { v, kind: 'cut', label: '用途重疊', cur, reasons, delta: -cur.usd };
  }
  if (hit === 'unknown') reasons.push('填上「多常撞到額度」，就能判斷要不要升降級。');
  if (uniq.length) reasons.push(`只有它在幫你做：${uniq.map((t) => tasks[t] || t).join('、')}。`);
  return { v, kind: 'keep', label: '維持', cur, reasons };
}
function monthly() {
  const p = prefs();
  let sum = 0;
  for (const v of Object.keys(S.d.plans?.vendors || {})) sum += planOf(v, p.tiers[v])?.usd || 0;
  return sum;
}

// ------------------------------------------------------------------ 首頁
function patchesFor(mode, vend) {
  const P = S.d.patches?.items || [];
  const R = S.d.meta?.rules || { show_min: 6, mine_min: 42 };
  let list = P.filter((x) => (vend === 'all' || x.v === vend));
  if (mode === 'mine') list = list.filter((x) => x.s >= R.mine_min && -dayDiff(x.d) <= 21).sort((a, b) => b.rk - a.rk);
  else list = list.filter((x) => x.s >= R.show_min);
  return list;
}
function renderHome() {
  const M = S.d.meta;
  const wk = M.week || '';
  const [y, w] = wk.split('.');
  const c = M.week_counts || {};
  const start = M.week_start;
  const end = start ? new Date(twDate(start).getTime() + 6 * 86400000).toISOString().slice(0, 10) : null;
  const mine = patchesFor('mine', 'all').slice(0, 5);
  const up = (S.d.patches?.upcoming || []).slice(0, 4);
  const G = S.d.guide?.tasks || [];
  const sum = monthly();
  let h = `
  <div class="patch" aria-label="本週版本 ${esc(wk)}">
    <div class="patch-k"><span>PATCH</span><span>${esc(md(start))}–${esc(md(end))}</span></div>
    <div class="patch-n num roll">${esc(y || '')}<span class="dotc">.</span>${esc(w || '')}</div>
    <div class="patch-d">這週的 AI 改版：四家 AI、本機工具、價格表一起看</div>
    <div class="patch-c">
      ${['buff', 'nerf', 'new', 'gone'].map((k) => `<a class="cnt" href="#/patch?fx=${k}"><span class="ico fx-${k}">${FX[k][0]}</span>${FX[k][1]} <b>${c[k] || 0}</b></a>`).join('')}
    </div>
    <div class="patch-mine">跟你有關的有 <b>${M.week_mine || 0}</b> 則${mine.length ? '，最重要的在下面' : ''}。</div>
  </div>
  ${serversHtml()}
  <h2 class="h2">跟你有關<span class="sub">依你的方案與用途排序</span><a class="more" href="#/patch">全部改版</a></h2>
  ${mine.length ? `<div class="pl">${mine.map((x) => patchCard(x, true)).join('')}</div>` : '<div class="empty">最近三週沒有跟你特別有關的改版。</div>'}`;
  if (up.length) {
    h += `<h2 class="h2">即將發生<span class="sub">漲價、停用的倒數</span><a class="more" href="#/patch?m=up">全部</a></h2><div>${up.map(cdRow).join('')}</div>`;
  }
  if (G.length) {
    h += `<h2 class="h2">你的版本答案<span class="sub">做什麼事用什麼</span><a class="more" href="#/guide">攻略</a></h2>
    <div class="tiers">${G.map((t) => {
      const p0 = (t.picks || [])[0] || {};
      return `<a class="trow" href="#/guide?t=${esc(t.id)}" style="text-decoration:none"><div class="trow-k"><b>${esc(t.short || t.name)}</b><span>${esc(TASK_ICON[t.id] || '')}</span></div>
      <div class="trow-v"><div class="trow-pick"><b>${esc(p0.tool || '')}${p0.model ? ` · ${esc(p0.model)}` : ''}</b><span>${esc(p0.plan || p0.why || '')}</span></div><i class="fresh-dot ${esc(t.fresh)}" title="${t.fresh === 'fresh' ? '答案還新鮮' : '有改版，答案可能要更新'}"></i></div></a>`;
    }).join('')}</div>`;
  }
  if (S.d.plans?.vendors) {
    const vs = Object.keys(S.d.plans.vendors).map(subVerdict).filter(Boolean);
    h += `<h2 class="h2">訂閱總帳<a class="more" href="#/shop">商城</a></h2>
    <a class="bill" href="#/shop" style="display:block;text-decoration:none">
      <div class="bill-top"><div><div class="note">每月 AI 訂閱</div><div class="bill-sum">${twd(toTwd(sum))}<small>約．${usd(sum)}</small></div></div></div>
      <div class="bill-rows">${vs.map((x) => `<div class="brow"><div class="brow-n">${vd(x.v)} ${esc(x.cur?.name || '')}</div><div class="brow-p"><span class="vchip ${esc(x.kind)}">${esc(x.label)}</span></div></div>`).join('')}</div>
    </a>`;
  }
  const L = S.d.local;
  if (L?.llm?.length) {
    const top = [...L.llm].map((m) => ({ m, f: llmFit(m) })).filter((x) => x.f && (x.f.level === 'easy' || x.f.level === 'tight'));
    h += `<h2 class="h2">你的筆電跑得動<span class="sub">${top.length} 個精選模型</span><a class="more" href="#/local">本機</a></h2>
    <div class="tools">${Object.values(L.tools || {}).slice(0, 4).map((t) => `<a class="tool" href="${esc(t.url || '#/local')}" target="_blank" rel="noopener"><b>${esc(t.name)} ${esc(t.ver || '')}</b><span>${esc(relDay(t.date || ''))}更新</span></a>`).join('')}</div>`;
  }
  h += footHtml();
  $('#v-home').innerHTML = h;
}
function serversHtml() {
  const st = S.d.status?.vendors || {};
  return `<div class="servers" role="list" aria-label="伺服器狀態">${['claude', 'chatgpt', 'gemini', 'grok'].map((v) => {
    const s = S.live[v] || st[v] || { ind: 'unknown' };
    return `<button type="button" class="srv ${esc(s.ind)}" data-srv="${v}" role="listitem"><span class="srv-n">${esc(VNAME[v])}</span><span class="srv-s"><i></i>${esc(ST[s.ind] || '讀不到')}</span></button>`;
  }).join('')}</div>`;
}
function cdRow(e) {
  const n = dayDiff(e.d);
  let t;
  let sub;
  if (e.type === 'retire') {
    t = `${esc(e.name)} 停用`;
    sub = e.replace ? `建議改用 ${esc(e.replace)}` : 'API 會停止服務';
  } else {
    t = `${esc(e.name)} ${e.up ? '漲價' : '降價'}`;
    sub = `輸入 ${usd(e.inp[0])}→${usd(e.inp[1])}、輸出 ${usd(e.out[0])}→${usd(e.out[1])}（每百萬 token）`;
  }
  const d = twDate(e.d);
  return `<div class="cd"><div class="cd-d"><b class="num">${d.getMonth() + 1}/${d.getDate()}</b><span>${WD[d.getDay()]}</span></div>
    <div class="cd-t">${vd(e.v)} ${t}<small>${sub}</small></div><div class="cd-left">${n <= 0 ? '今天' : `${n} 天`}</div></div>`;
}

// ------------------------------------------------------------------ 改版公告
function patchCard(x, showWhy) {
  const src = S.d.meta?.sources?.[x.src];
  const prod = x.p || src?.p || '';
  const title = x.tz || x.t;
  const sum = x.sz || (x.tz ? '' : (x.b || '').slice(0, 140));
  const open = S.open.has(x.id);
  const also = (x.also || []).map((a) => a.p).filter((v, i, a) => a.indexOf(v) === i);
  return `<article class="pc f-${esc(x.fx)}${x.s < (S.d.meta?.rules?.mine_min || 42) && !showWhy ? ' dim' : ''}${open ? ' open' : ''}" data-pid="${esc(x.id)}" tabindex="0" aria-expanded="${open}">
    <div class="pc-h">${fxChip(x.fx)}${vd(x.v, prod)}<span class="when">${esc(relDay(x.d))}</span></div>
    <h3 class="pc-t">${esc(title)}${x.pend ? ' <span class="pend">翻譯中</span>' : ''}</h3>
    ${sum ? `<p class="pc-s"${x.tz ? '' : ' lang="en"'}>${esc(sum)}</p>` : ''}
    ${showWhy && x.why?.length ? `<div class="pc-w">${x.why.map((w) => `<span class="why">${esc(w)}</span>`).join('')}</div>` : ''}
    <div class="pc-x">
      ${x.zh_native ? '' : `<div class="orig" lang="en"><b>原文</b> ${esc(x.t)}${x.b && x.b !== x.t ? ` — ${esc(x.b)}` : ''}</div>`}
      ${x.hl?.length ? `<div class="orig" lang="en" style="margin-top:6px">${x.n_add ? `新增 ${x.n_add} 項、` : ''}${x.n_fix ? `修正 ${x.n_fix} 項` : ''}</div>` : ''}
      <div class="tags">${(x.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join('')}<span class="tag">分數 ${x.s}</span></div>
      ${also.length ? `<div class="note">同一件事也出現在：${esc(also.join('、'))}</div>` : ''}
      <div class="btn-row">${x.url ? `<a class="btn sm" href="${esc(x.url)}" target="_blank" rel="noopener">看官方原文</a>` : ''}<button type="button" class="btn sm ghost" data-ask-patch="${esc(x.id)}">找 Claude 討論</button></div>
    </div>
  </article>`;
}
function renderPatch() {
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  if (q.get('m') === 'up') S.pm = 'up';
  const fxF = q.get('fx');
  const vs = ['all', 'claude', 'chatgpt', 'gemini', 'grok', 'local'];
  let h = `<h1 class="h1">改版公告</h1><p class="lede">四家 AI 與本機工具的官方更新紀錄，自動翻成中文。綠色加強、紅色削弱、藍色新增、紫色移除。</p>
  <div class="seg" role="group" aria-label="顯示方式">
    <button type="button" data-pm="mine" aria-pressed="${S.pm === 'mine'}">跟我有關</button>
    <button type="button" data-pm="all" aria-pressed="${S.pm === 'all'}">全部</button>
    <button type="button" data-pm="up" aria-pressed="${S.pm === 'up'}">即將發生</button>
  </div>
  <div class="chips" role="group" aria-label="篩選">${vs.map((v) => `<button type="button" class="chip" data-pv="${v}" aria-pressed="${S.pv === v}">${v === 'all' ? '全部' : vd(v)}</button>`).join('')}</div>`;
  if (S.pm === 'up') {
    const up = (S.d.patches?.upcoming || []).filter((e) => S.pv === 'all' || e.v === S.pv);
    h += up.length ? `<div>${up.map(cdRow).join('')}</div>` : '<div class="empty">接下來四個月沒有已公布的漲價或停用。</div>';
    h += '<p class="note" style="margin-top:12px">資料來自官方價格頁上的「限時價格」與官方停用表。</p>';
  } else {
    let list = patchesFor(S.pm, S.pv);
    if (fxF && FX[fxF]) {
      list = list.filter((x) => x.fx === fxF && x.d >= (S.d.meta.week_start || ''));
      h += `<div class="warnbox">只看本週的「${FX[fxF][1]}」。<a href="#/patch" class="linkbtn">看全部</a></div>`;
    }
    if (!list.length) h += '<div class="empty">這個篩選沒有改版。</div>';
    else if (S.pm === 'mine' && !fxF) h += `<div class="pl" style="margin-top:8px">${list.slice(0, 40).map((x) => patchCard(x, true)).join('')}</div>`;
    else {
      let last = '';
      h += list.slice(0, 160).map((x) => {
        const head = x.d !== last ? `<div class="datehead">${esc(mdw(x.d))}</div>` : '';
        last = x.d;
        return head + patchCard(x, false);
      }).join('');
      const hidden = (S.d.patches?.items || []).filter((x) => x.s < (S.d.meta?.rules?.show_min || 6)).length;
      if (hidden) h += `<p class="note" style="margin-top:14px">另有 ${hidden} 則公司新聞稿、客戶案例、企業版功能，跟你的使用沒有直接關係，已收起來。</p>`;
    }
  }
  h += footHtml();
  $('#v-patch').innerHTML = h;
}

// ------------------------------------------------------------------ 商城
function renderShop() {
  const PL = S.d.plans;
  if (!PL?.vendors) { $('#v-shop').innerHTML = '<div class="empty">方案資料還沒準備好。</div>'; return; }
  const p = prefs();
  const sum = monthly();
  const vs = Object.keys(PL.vendors);
  let h = `<h1 class="h1">商城</h1><p class="lede">你的訂閱帳單、四家方案比較、API 價格表。台幣是用當天匯率換算的參考值。</p>
  <div class="bill">
    <div class="bill-top"><div><div class="note">每月 AI 訂閱</div><div class="bill-sum">${twd(toTwd(sum))}<small>約．${usd(sum)}</small></div></div>
    <button type="button" class="btn sm" data-sheet="settings">改我的方案</button></div>
    <div class="bill-rows">${vs.map((v) => {
      const x = subVerdict(v);
      const cur = x?.cur;
      return `<div class="brow" data-verdict="${v}"><div class="brow-n">${vd(v)} ${esc(cur?.name || '')}</div>
      <div class="brow-p">${cur?.usd ? `${usd(cur.usd)}<small>${twd(toTwd(cur.usd))}／月</small>` : '免費'}</div>
      <div class="brow-r"><span class="vchip ${esc(x?.kind)}">${esc(x?.label || '')}</span><span>${esc((x?.reasons || [])[0] || '')}</span></div></div>`;
    }).join('')}</div>
  </div>
  <p class="note" style="margin-top:8px">${PL.fx ? `匯率 1 美元 ≈ ${PL.fx.usd_twd} 台幣（${esc(PL.fx.src)}）。信用卡刷外幣另有約 1.5% 海外交易手續費；部分方案在台灣另加營業稅。` : '匯率暫時讀不到。'}</p>`;
  h += `<h2 class="h2">四家方案<span class="sub">人工核對 ${esc(PL.checked || '')}</span></h2>
  <div class="vtabs" role="group" aria-label="選擇廠商">${vs.map((v) => `<button type="button" class="chip" data-shopv="${v}" aria-pressed="${S.shopV === v}">${vd(v)}</button>`).join('')}</div>`;
  const V = PL.vendors[S.shopV];
  if (V) {
    if (V.page_changes?.length) h += `<div class="warnbox">${esc(V.name)} 官方方案頁在 ${esc(md(V.page_changes[0].changed_at))} 有變動（${V.page_changes[0].basis === 'prices' ? '價格數字變了' : '額度相關文字變了'}），下面的表可能要更新。<a href="${esc(V.page_changes[0].url)}" target="_blank" rel="noopener">看官方頁</a></div>`;
    h += `<div class="plans">${V.plans.map((pl) => {
      const mine = p.tiers[S.shopV] === pl.id;
      return `<div class="plan${mine ? ' mine' : ''}">
        <div class="plan-n"><span>${esc(pl.name)}</span>${mine ? '<span class="plan-mine">你的方案</span>' : ''}</div>
        <div class="plan-p">${pl.usd ? usd(pl.usd) : '免費'}${pl.usd ? '<small> ／月</small>' : ''}</div>
        ${pl.usd ? `<div class="plan-tw">約 ${twd(pl.twd)}${pl.twd_ios ? `；iOS 台灣 App Store NT$${pl.twd_ios}` : ''}${pl.usd_year ? `；年繳每月 ${usd(pl.usd_year)}` : ''}</div>` : ''}
        ${pl.limits?.length ? `<ul>${pl.limits.map((l) => `<li class="lim">${esc(l)}</li>`).join('')}</ul>` : ''}
        ${pl.gets?.length ? `<ul>${pl.gets.map((l) => `<li>${esc(l)}</li>`).join('')}</ul>` : ''}
        ${pl.src?.length ? `<div class="plan-src">來源：${pl.src.map((s, i) => `<a href="${esc(s)}" target="_blank" rel="noopener">官方${i ? i + 1 : ''}</a>`).join('、')}</div>` : ''}
      </div>`;
    }).join('')}</div>`;
    if (V.unique?.length) h += `<div class="card" style="margin-top:12px"><h3>${esc(V.name)} 才有的</h3><ul>${V.unique.map((u) => `<li>${esc(u)}</li>`).join('')}</ul></div>`;
    if (V.app?.ver) h += `<p class="note">iOS App 最新版 ${esc(V.app.ver)}（${esc(md(V.app.date))}）</p>`;
  }
  // API 價格
  const models = S.d.prices?.models || [];
  h += `<h2 class="h2">API 價格表<span class="sub">每百萬 token，美元</span></h2>
  <p class="lede">直接讀四家官方價格頁。做自己的 App、用 API 跑東西時才會用到，跟訂閱是兩回事。</p>`;
  for (const v of ['claude', 'chatgpt', 'gemini', 'grok']) {
    const ms = models.filter((m) => m.v === v && m.main).sort((a, b) => (b.out || 0) - (a.out || 0));
    if (!ms.length) continue;
    h += `<h3 style="margin:16px 0 4px;font-size:15px">${vd(v)}</h3><table class="ptable"><thead><tr><th>模型</th><th>輸入</th><th>輸出</th><th>快取讀取</th></tr></thead><tbody>${ms.map((m) => {
      const chg = m.chg ? `<span class="pchg ${m.chg.to > m.chg.from ? 'up' : 'down'}">${m.chg.to > m.chg.from ? '漲' : '降'}</span>` : '';
      const fut = m.fut?.from ? `<span class="pchg fut">${md(m.fut.from)} 起 ${usd(m.fut.inp)}／${usd(m.fut.out)}</span>` : '';
      return `<tr><td><span class="mname">${esc(m.name)}</span>${m.tier ? `<span class="tierlbl">${esc(m.tier)}</span>` : ''}${chg}<span class="msub">${esc([m.role, m.note, m.ctx ? `上下文 ${String(m.ctx).replace(' tokens', '')}` : ''].filter(Boolean).join('．'))}</span>${fut ? `<span class="msub">${fut}</span>` : ''}</td>
      <td>${usd(m.inp)}</td><td>${usd(m.out)}</td><td>${usd(m.cr)}</td></tr>`;
    }).join('')}</tbody></table>`;
  }
  h += `<button type="button" class="linkbtn" data-sheet="allmodels" style="margin-top:10px">看全部型號（含舊型號與停用日期）</button>`;
  h += calcHtml();
  h += footHtml();
  $('#v-shop').innerHTML = h;
}
function calcHtml() {
  const ms = (S.d.prices?.models || []).filter((m) => m.main && m.inp != null);
  if (!ms.length) return '';
  const c = S.calc || (S.calc = { id: (ms.find((m) => m.v === 'claude' && m.fam === 'sonnet') || ms[0]).id, inp: 200, out: 40, days: 30 });
  const m = ms.find((x) => x.id === c.id) || ms[0];
  const cost = (c.inp / 1000 * m.inp + c.out / 1000 * m.out) * c.days;
  return `<h2 class="h2">API 試算</h2><div class="calc">
    <label class="field">模型<select data-calc="id">${ms.map((x) => `<option value="${esc(x.id)}"${x.id === m.id ? ' selected' : ''}>${esc(VNAME[x.v])}．${esc(x.name)}</option>`).join('')}</select></label>
    <div class="row2"><label class="field">每天輸入（千 token）<input type="number" min="0" step="10" value="${c.inp}" data-calc="inp"></label>
    <label class="field">每天輸出（千 token）<input type="number" min="0" step="5" value="${c.out}" data-calc="out"></label></div>
    <div class="calc-out">${usd(cost)} ／月<small>約 ${twd(toTwd(cost))}；以每月 ${c.days} 天、官方標準價、沒用快取計算。一千 token 大約一千三百個中文字。</small></div>
  </div>`;
}

// ------------------------------------------------------------------ 本機
function licChip(c) { const t = { yes: '可商用', cond: '有條件商用', no: '不可商用' }[c] || '授權未明'; return `<span class="lic ${esc(c || '')}">${t}</span>`; }
function renderLocal() {
  const L = S.d.local;
  if (!L?.rig) { $('#v-local').innerHTML = '<div class="empty">本機資料還沒準備好。</div>'; return; }
  const r = L.rig;
  const p = prefs();
  const ctxs = [4096, 8192, 16384, 32768, 65536, 131072];
  const ci = Math.max(0, ctxs.indexOf(p.ctx));
  const cats = L.cats || [];
  let h = `<h1 class="h1">本機</h1><p class="lede">哪些開源模型在你的筆電跑得動、吃多少顯示記憶體、大概多快。檔案大小每天從 Hugging Face 自動更新。</p>
  <div class="rig"><div class="rig-n"><b>${esc(r.gpu || 'RTX 5090 Laptop GPU')}</b><span>${esc(r.name || '')}</span></div>
    <div class="rig-specs"><span>顯示記憶體 <b>${r.vram_gib} GB</b>（模型可用 ${r.vram_gib - r.vram_reserve_gib}）</span><span>系統記憶體 <b>${r.ram_gib} GB</b></span><span>硬碟剩 <b>${r.disk_free_gb || '—'} GB</b></span></div>
    <div class="knobs">
      <div><div class="knob-l"><span>對話長度（上下文）</span><b>${ctxLabel(p.ctx)}．${ctxChars(p.ctx)}</b></div><input type="range" min="0" max="${ctxs.length - 1}" step="1" value="${ci}" data-knob="ctx" aria-label="對話長度"></div>
      <div class="knob-l"><span>對話記憶壓縮（KV cache）</span><span class="seg" role="group"><button type="button" data-kvq="f16" aria-pressed="${p.kvq === 'f16'}">原版</button><button type="button" data-kvq="q8_0" aria-pressed="${p.kvq === 'q8_0'}">壓縮一半</button></span></div>
    </div>
    <div class="vlegend"><span><i style="background:var(--t-d)"></i>模型本體</span><span><i style="background:var(--t-c)"></i>對話記憶</span><span><i style="background:var(--ink3)"></i>運算暫存</span><span><i style="background:var(--t-a)"></i>放不下、借系統記憶體</span><span>直線＝顯卡上限</span></div>
  </div>
  <div class="chips" role="group" aria-label="用途">${cats.map((c) => `<button type="button" class="chip" data-lcat="${esc(c.id)}" aria-pressed="${S.lcat === c.id}">${esc(c.name)}</button>`).join('')}<button type="button" class="chip" data-lcat="found" aria-pressed="${S.lcat === 'found'}">新上架</button></div>`;
  if (S.lcat === 'found') h += foundHtml();
  else if (S.lcat === 'image' || S.lcat === 'video') {
    const ds = (L.diffusion || []).filter((m) => m.kind === S.lcat);
    h += ds.length ? `<div class="ml">${ds.map((m) => { const f = diffFit(m); return `<div class="mr" data-dm="${esc(m.id)}" tabindex="0">
      <div class="mr-n"><b>${esc(m.name)}</b><span>${esc(m.maker || '')}．${esc(f?.variant?.prec || '')} ${f ? `${f.variant.gib.toFixed(1)} GB` : ''}</span></div>
      <div class="mr-side">${f ? `<span class="vchip ${f.level}">${LV_SHORT[f.level]}</span>` : ''}<span class="mr-tps">${esc(m.speed_short || '')}</span></div>
      ${vbar(f)}<div class="mr-meta">${licChip(m.commercial)}${(m.features || []).slice(0, 3).map((x) => `<span>${esc(x)}</span>`).join('．')}</div></div>`; }).join('')}</div>` : '<div class="empty">這一類還沒有精選模型。</div>';
  } else {
    const ms = (L.llm || []).filter((m) => (m.cats || []).includes(S.lcat));
    const rows = ms.map((m) => ({ m, f: llmFit(m) })).sort((a, b) => (a.m.order ?? 99) - (b.m.order ?? 99));
    h += rows.length ? `<div class="ml">${rows.map(({ m, f }) => `<div class="mr" data-lm="${esc(m.id)}" tabindex="0">
      <div class="mr-n"><b>${esc(m.name)}</b><span>${esc(m.maker || '')}．${esc(m.size_note || (m.active_b ? `${m.total_b}B（每次用 ${m.active_b}B）` : `${m.total_b}B`))}${f ? `．${esc(f.q)} ${f.weights.toFixed(1)} GB` : ''}</span></div>
      <div class="mr-side">${f ? `<span class="vchip ${f.level}">${LV_SHORT[f.level]}</span><span class="mr-tps">約 ${Math.round(f.tps)} token/秒</span>` : '<span class="vchip ask">檔案未齊</span>'}</div>
      ${vbar(f)}<div class="mr-meta">${licChip(m.commercial)}<span>${esc(m.good || '')}</span></div></div>`).join('')}</div>` : '<div class="empty">這一類還沒有精選模型。</div>';
  }
  const T = L.tools || {};
  h += `<h2 class="h2">本機工具最新版</h2><div class="tools">${Object.values(T).map((t) => `<a class="tool" href="${esc(t.url || '#')}" target="_blank" rel="noopener"><b>${esc(t.name)} ${esc(t.ver || '')}</b><span>${esc(t.date ? relDay(t.date) : '')}${t.date ? '發布' : ''}</span></a>`).join('')}</div>`;
  h += '<p class="note" style="margin-top:12px">速度是用記憶體頻寬推算的生成速度（token／秒，中文一個字約 0.8 token），實際會因設定與散熱上下浮動兩三成。筆電插電、開效能模式最準。</p>';
  h += footHtml();
  $('#v-local').innerHTML = h;
}
function foundHtml() {
  const F = S.d.local?.found || [];
  if (!F.length) return '<div class="empty">最近兩個月沒有知名團隊的新模型衝上 Hugging Face 熱門。</div>';
  return `<p class="note">Hugging Face 熱門、60 天內發布、知名團隊的官方模型（自動抓，還沒人工挑過）。判定是用參數量估算的。</p><div class="ml">${F.map((c) => `<a class="mr" href="${esc(c.url)}" target="_blank" rel="noopener" style="text-decoration:none">
    <div class="mr-n"><b>${esc(c.id.split('/')[1])}</b><span>${esc(c.id.split('/')[0])}．${c.params_b}B${c.active_b ? `（每次用 ${c.active_b}B）` : ''}．${esc({ llm: '語言模型', image: '生圖', video: '生影片' }[c.kind] || '')}．${esc(md(c.created))} 發布</span></div>
    <div class="mr-side">${c.fit ? `<span class="vchip ${c.fit.level}">${LV_SHORT[c.fit.level]}</span>` : ''}<span class="mr-tps">${c.kind === 'llm' ? (c.gguf ? '有 GGUF' : '還沒 GGUF') : ''}</span></div>
    <div class="mr-meta"><span>${esc(c.fit?.q || '')} 約 ${c.fit ? c.fit.need.toFixed(1) : '—'} GB</span>${c.license ? `<span>授權 ${esc(c.license)}</span>` : ''}</div></a>`).join('')}</div>`;
}

// ------------------------------------------------------------------ 攻略
function renderGuide() {
  const G = S.d.guide;
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  const focus = q.get('t');
  let h = `<h1 class="h1">攻略</h1><p class="lede">現在這個版本，做什麼事用什麼。每一個答案都寫了理由；四家一有相關改版，答案旁的燈號會變黃或紅，提醒你回來複查。</p>`;
  if (G?.tasks?.length) {
    h += `<h2 class="h2">版本答案<span class="sub">人工複查 ${esc(G.reviewed || '')}</span></h2>`;
    h += G.tasks.map((t) => `<div class="task" id="task-${esc(t.id)}"${focus === t.id ? ' style="border-color:var(--t-b)"' : ''}>
      <div class="task-h"><b>${esc(t.name)}</b><i class="fresh-dot ${esc(t.fresh)}"></i></div>
      ${t.lede ? `<p class="lede" style="margin:6px 0 0">${esc(t.lede)}</p>` : ''}
      <div class="picks">${(t.picks || []).map((pk) => {
        const lm = pk.local_id ? [...(S.d.local?.llm || []), ...(S.d.local?.diffusion || [])].find((m) => m.id === pk.local_id) : null;
        const f = lm ? (lm.kind ? diffFit(lm) : llmFit(lm)) : null;
        const rk = pk.rank === '本機' ? 'local' : pk.rank === '不推' ? 'skip' : pk.rank;
        return `<div class="pick"><span class="tb tb-${esc(rk)}">${esc(pk.rank)}</span>
          <div class="pick-n">${pk.v ? vd(pk.v, pk.tool) : esc(pk.tool || '')}${pk.model ? ` <small>${esc(pk.model)}</small>` : ''}${f ? ` <span class="vchip ${f.level}" style="margin-left:4px">${LV_SHORT[f.level]}</span>` : ''}</div>
          <div class="pick-w">${esc(pk.why || '')}</div>${pk.plan ? `<div class="pick-p">${esc(pk.plan)}</div>` : ''}</div>`;
      }).join('')}</div>
      ${t.tips?.length ? `<ul class="tips">${t.tips.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${t.flags?.length ? `<div class="flags ${t.fresh === 'stale' ? 'stale' : ''}"><b>${t.fresh === 'stale' ? '這個答案可能過時了' : '有新改版，值得複查'}</b><ul>${t.flags.map((f) => `<li>${esc(f.text)}${f.items ? `：${f.items.map((i) => esc(i.t)).join('；')}` : ''}</li>`).join('')}</ul></div>` : ''}
      <div class="btn-row"><button type="button" class="btn sm ghost" data-ask-task="${esc(t.id)}">找 Claude 重新評估</button></div>
    </div>`).join('');
  }
  // 訂閱方針
  const vs = Object.keys(S.d.plans?.vendors || {});
  if (vs.length) {
    h += `<h2 class="h2">訂閱方針<span class="sub">照你填的用途與撞額度頻率判斷</span></h2><div class="card">${vs.map((v) => {
      const x = subVerdict(v);
      return `<div class="verdict"><div class="verdict-n">${vd(v)} ${esc(x.cur?.name || '')}</div><span class="vchip ${esc(x.kind)}">${esc(x.label)}</span>
        <div class="verdict-r"><ul>${x.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></div></div>`;
    }).join('')}<div class="btn-row"><button type="button" class="btn primary sm" data-sheet="settings">填用途與撞額度頻率</button></div></div>`;
  }
  if (G?.cards?.length) {
    h += '<h2 class="h2">方針</h2>' + G.cards.map((c) => `<div class="card" id="card-${esc(c.id)}"><h3>${esc(c.title)}</h3>${c.lede ? `<p class="lede" style="margin:0">${esc(c.lede)}</p>` : ''}
      <${c.ordered ? 'ol' : 'ul'}>${(c.items || []).map((i) => `<li>${i.b ? `<b>${esc(i.b)}</b>　` : ''}${esc(i.t || i)}</li>`).join('')}</${c.ordered ? 'ol' : 'ul'}>
      ${c.src?.length ? `<div class="src">依據：${c.src.map((s) => `<a href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t)}</a>`).join('、')}</div>` : ''}</div>`).join('');
  }
  h += footHtml();
  $('#v-guide').innerHTML = h;
  if (focus) setTimeout(() => $(`#task-${CSS.escape(focus)}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 60);
}

// ------------------------------------------------------------------ 抽屜
function openSheet(html) {
  const w = $('#sheet');
  $('#sheet-body').innerHTML = html;
  w.hidden = false;
  document.body.style.overflow = 'hidden';
  $('.sheet', w).focus();
}
function closeSheet() { $('#sheet').hidden = true; document.body.style.overflow = ''; }
const sheetTop = (title) => `<div class="sh-top"><span class="sp"></span><button type="button" class="ibtn" data-close aria-label="關閉">${ICON.close}</button></div><h2 class="sh-title" id="sh-title">${title}</h2>`;
function serverSheet(v) {
  const s = S.live[v] || S.d.status?.vendors?.[v];
  if (!s) return;
  const live = S.live[v] ? '（剛剛直接向官方狀態頁確認）' : `（${ago(S.d.status.generated)}的資料）`;
  openSheet(`${sheetTop(`${esc(VNAME[v])} 伺服器：${esc(ST[s.ind] || '')}`)}
    <p class="note">${esc(live)}</p>${s.note ? `<p class="lede">${esc(s.note)}</p>` : ''}
    ${s.active?.length ? `<div class="sh-sec"><h3>進行中的狀況</h3>${s.active.map((a) => `<div class="warnbox" lang="en">${esc(a.t)}</div>`).join('')}</div>` : ''}
    ${s.comps?.length ? `<div class="sh-sec"><h3>各項服務</h3><div class="health">${s.comps.map((c) => `<span>${esc(c.n)}</span><span class="${c.s === 'ok' ? 'ok' : 'bad'}">${esc(ST[c.s] || c.s)}</span>`).join('')}</div></div>` : ''}
    <div class="sh-sec"><h3>最近 7 天的事故（${s.n7 ?? '—'} 次）</h3>${(s.recent || []).length ? s.recent.map((r) => `<div class="cd"><div class="cd-d"><b class="num">${esc(md(r.at))}</b><span>${esc(ST[r.impact] || '')}</span></div><div class="cd-t" lang="en">${esc(r.t)}<small>${r.mins ? `持續 ${r.mins >= 120 ? `${Math.round(r.mins / 60)} 小時` : `${r.mins} 分鐘`}` : '處理中'}</small></div><span></span></div>`).join('') : '<p class="note">沒有事故。</p>'}</div>
    <div class="btn-row"><a class="btn" href="${esc(s.page)}" target="_blank" rel="noopener">開官方狀態頁</a></div>`);
}
function llmSheet(id, q) {
  const m = (S.d.local?.llm || []).find((x) => x.id === id);
  if (!m) return;
  q = q || pickQuant(m);
  const f = llmFit(m, q);
  const p = prefs();
  const qs = Object.entries(m.quants || {}).filter(([k]) => S.d.local.quants?.[k]).sort((a, b) => a[1] - b[1]);
  const lab = (k) => S.d.local.quants?.[k]?.zh || k;
  openSheet(`${sheetTop(esc(m.name))}
    <p class="lede">${esc(m.maker || '')}．${esc(m.size_note || (m.active_b ? `總共 ${m.total_b}B 參數，每次只用 ${m.active_b}B（MoE）` : `${m.total_b}B 參數`))}．${licChip(m.commercial)}</p>
    ${m.zh ? `<p>${esc(m.zh)}</p>` : ''}
    ${f ? `<div class="sh-sec"><h3>在你的筆電：<span class="vchip ${f.level}">${LV[f.level]}</span></h3>
      ${vbar(f, true)}
      <dl class="kv" style="margin-top:10px"><dt>總共需要</dt><dd class="num">${f.need.toFixed(1)} GB（顯卡可用 ${f.usable.toFixed(0)} GB）</dd>
      <dt>模型本體</dt><dd class="num">${f.weights.toFixed(1)} GB（${esc(q)}）</dd><dt>對話記憶</dt><dd class="num">${f.kv.toFixed(1)} GB（${ctxLabel(f.ctx)}，${esc(p.kvq === 'f16' ? '原版' : '壓縮一半')}）</dd>
      <dt>運算暫存</dt><dd class="num">${f.compute.toFixed(1)} GB</dd>${f.spill > 0 ? `<dt>放不下的</dt><dd class="num">${f.spill.toFixed(1)} GB 借系統記憶體</dd>` : ''}
      <dt>速度</dt><dd><b class="num">約 ${Math.round(f.tps)} token／秒</b>．${speedWord(f.tps)}</dd></dl>
      ${f.level === 'offload' ? `<p class="note">${f.moe ? '這是 MoE 模型，把「專家層」放到系統記憶體（LM Studio 的「Offload experts to CPU」、llama.cpp 的 --n-cpu-moe）速度還能接受。' : '一般模型放不下時會慢很多；建議換小一級的壓縮或縮短對話長度。'}</p>` : ''}
    </div>` : '<p class="empty">還沒取得這個模型的檔案大小。</p>'}
    ${qs.length ? `<div class="sh-sec"><h3>壓縮等級</h3><div class="qsel">${qs.map(([k, g]) => `<button type="button" data-q="${esc(k)}" data-lmq="${esc(m.id)}" aria-pressed="${k === q}">${esc(k)}<small>${g.toFixed(1)} GB．${esc(lab(k))}</small></button>`).join('')}</div>
      <p class="note" style="margin-top:6px">數字越小越省空間、品質掉一點；Q4_K_M 是大家公認的甜蜜點。</p></div>` : ''}
    ${m.good ? `<div class="sh-sec"><h3>適合拿來做</h3><p>${esc(m.good)}</p></div>` : ''}
    ${m.notes?.length ? `<div class="sh-sec"><h3>要注意</h3><ul>${m.notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul></div>` : ''}
    <div class="sh-sec"><h3>怎麼裝</h3>
      ${m.lms ? `<p class="note">LM Studio：左邊放大鏡搜尋這串，選 ${esc(q)} 下載</p><div class="cmd"><code>${esc(m.lms)}</code><button type="button" data-copy="${esc(m.lms)}">複製</button></div>` : ''}
      ${m.ollama ? `<p class="note" style="margin-top:8px">Ollama：在終端機貼上</p><div class="cmd"><code>ollama run ${esc(m.ollama)}</code><button type="button" data-copy="ollama run ${esc(m.ollama)}">複製</button></div>` : ''}
    </div>
    <div class="btn-row">${m.hf ? `<a class="btn sm" href="https://huggingface.co/${esc(m.hf)}" target="_blank" rel="noopener">官方模型頁</a>` : ''}${m.gguf ? `<a class="btn sm" href="https://huggingface.co/${esc(m.gguf)}" target="_blank" rel="noopener">GGUF 檔案</a>` : ''}<button type="button" class="btn sm ghost" data-ask-model="${esc(m.id)}">找 Claude 討論</button></div>
    ${m.src?.length ? `<p class="src">依據：${m.src.map((s) => `<a href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t)}</a>`).join('、')}</p>` : ''}`);
}
function diffSheet(id, vi) {
  const m = (S.d.local?.diffusion || []).find((x) => x.id === id);
  if (!m) return;
  vi = vi ?? m.rec ?? 0;
  const f = diffFit(m, vi);
  openSheet(`${sheetTop(esc(m.name))}
    <p class="lede">${esc(m.maker || '')}．${esc({ image: '生圖', video: '生影片' }[m.kind])}．${licChip(m.commercial)}</p>
    ${m.zh ? `<p>${esc(m.zh)}</p>` : ''}
    ${f ? `<div class="sh-sec"><h3>在你的筆電：<span class="vchip ${f.level}">${LV[f.level]}</span></h3>${vbar(f, true)}
      <dl class="kv" style="margin-top:10px"><dt>最高需要</dt><dd class="num">約 ${f.need.toFixed(1)} GB</dd><dt>模型本體</dt><dd class="num">${f.weights.toFixed(1)} GB（${esc(f.variant.prec)}）</dd>
      <dt>生成暫存</dt><dd class="num">約 ${f.kv.toFixed(1)} GB（${esc(m.typical || '')}）</dd>${f.te ? `<dt>文字編碼器</dt><dd class="num">${f.te.toFixed(1)} GB（先用完再換下，不同時占用）</dd>` : ''}
      ${m.speed ? `<dt>速度</dt><dd>${esc(m.speed)}</dd>` : ''}</dl></div>` : ''}
    ${(m.variants || []).length > 1 ? `<div class="sh-sec"><h3>版本</h3><div class="qsel">${m.variants.map((v, i) => `<button type="button" data-dmv="${i}" data-dm2="${esc(m.id)}" aria-pressed="${i === vi}">${esc(v.prec)}<small>${v.gib.toFixed(1)} GB${v.note ? `．${esc(v.note)}` : ''}</small></button>`).join('')}</div></div>` : ''}
    ${m.features?.length ? `<div class="sh-sec"><h3>能做什麼</h3><ul>${m.features.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
    ${m.notes?.length ? `<div class="sh-sec"><h3>要注意</h3><ul>${m.notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul></div>` : ''}
    <div class="sh-sec"><h3>怎麼用</h3><p>${esc(m.comfyui || '在 ComfyUI 的範本（Templates）裡找得到。')}</p></div>
    <div class="btn-row">${m.hf ? `<a class="btn sm" href="https://huggingface.co/${esc(m.hf)}" target="_blank" rel="noopener">官方模型頁</a>` : ''}<button type="button" class="btn sm ghost" data-ask-model="${esc(m.id)}">找 Claude 討論</button></div>
    ${m.src?.length ? `<p class="src">依據：${m.src.map((s) => `<a href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t)}</a>`).join('、')}</p>` : ''}`);
}
function verdictSheet(v) {
  const x = subVerdict(v);
  const V = S.d.plans.vendors[v];
  openSheet(`${sheetTop(`${esc(V.name)}：${esc(x.label)}`)}<ul>${x.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
    <div class="btn-row"><button type="button" class="btn primary sm" data-sheet="settings">改用途與撞額度頻率</button><button type="button" class="btn sm" data-shopv-go="${esc(v)}">看 ${esc(V.name)} 方案</button></div>`);
}
function allModelsSheet() {
  const ms = S.d.prices?.models || [];
  openSheet(`${sheetTop('全部 API 型號')}<p class="note">灰色是舊型號；停用日期來自官方停用表。</p>${['claude', 'chatgpt', 'gemini', 'grok'].map((v) => {
    const list = ms.filter((m) => m.v === v);
    if (!list.length) return '';
    return `<h3 style="margin:16px 0 4px;font-size:15px">${vd(v)}</h3><table class="ptable"><thead><tr><th>型號</th><th>輸入</th><th>輸出</th></tr></thead><tbody>${list.map((m) => `<tr class="${m.main ? '' : 'old'}"><td><span class="mname">${esc(m.name)}</span><span class="msub">${esc(m.id)}${m.status && m.status !== 'active' ? `．${esc({ deprecated: '已列入停用', retired: '已停用', preview: '預覽版', legacy: '舊版' }[m.status] || m.status)}` : ''}${m.retire && !/sooner|announced|N\/A/i.test(m.retire) ? `．${esc(m.retire)} 停用` : ''}</span></td><td>${usd(m.inp)}</td><td>${usd(m.out)}</td></tr>`).join('')}</tbody></table>`;
  }).join('')}`);
}
function settingsSheet() {
  const p = prefs();
  const PL = S.d.plans?.vendors || {};
  const tasks = S.d.plans?.tasks || {};
  const key = lsGet(KEY_KEY);
  openSheet(`${sheetTop('我的設定')}<p class="note">只存在這台裝置。換手機或電腦時，用最下面的「備份」搬過去。</p>
    ${Object.keys(PL).map((v) => `<div class="set-group"><h3>${vd(v)}</h3>
      <div class="set-row"><span>目前方案</span><select data-pref="tier" data-v="${v}">${PL[v].plans.map((pl) => `<option value="${esc(pl.id)}"${p.tiers[v] === pl.id ? ' selected' : ''}>${esc(pl.name)}${pl.usd ? `（${usd(pl.usd)}）` : ''}</option>`).join('')}</select></div>
      ${(planOf(v, p.tiers[v])?.usd || 0) > 0 ? `<div class="set-row"><span>多常撞到額度上限</span><select data-pref="hits" data-v="${v}">${Object.entries(HITS).map(([k, l]) => `<option value="${k}"${(p.hits[v] || 'unknown') === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></div>` : ''}
      <div class="set-row" style="border:0"><span>拿它做什麼</span><span></span><div class="checks">${Object.entries(tasks).map(([k, l]) => `<label><input type="checkbox" data-pref="use" data-v="${v}" value="${k}"${(p.uses[v] || []).includes(k) ? ' checked' : ''}>${esc(l)}</label>`).join('')}</div></div>
    </div>`).join('')}
    <div class="set-group"><h3>外觀</h3><div class="set-row"><span>深色／淺色</span><select data-pref="theme"><option value="auto"${p.theme === 'auto' ? ' selected' : ''}>跟著手機</option><option value="dark"${p.theme === 'dark' ? ' selected' : ''}>深色</option><option value="light"${p.theme === 'light' ? ' selected' : ''}>淺色</option></select></div></div>
    <div class="set-group"><h3>遙控鑰匙</h3><p class="lede">資料每小時自動更新。想隨時按「更新」叫 GitHub 立刻重抓一輪（約 5 分鐘），需要一把只能控制 ai-meta 這個 repo 的鑰匙。</p>
      ${key ? '<div class="btn-row"><button type="button" class="btn sm" data-key-del>移除這台裝置的鑰匙</button></div>' : `<ol class="tips"><li>登入 GitHub，打開 <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">建立新鑰匙</a>（Fine-grained token）。</li><li>名稱填「版本答案遙控鑰匙」，期限選最長；Repository access 選 Only select repositories → ai-meta。</li><li>Permissions 的 Actions 選 Read and write，其他不用動，按 Generate token。</li><li>複製那串字貼到下面。鑰匙只存在這台裝置。</li></ol>
      <div class="field" style="margin-top:8px"><input type="password" id="key-in" placeholder="github_pat_…" autocomplete="off"></div><div class="btn-row"><button type="button" class="btn primary sm" data-key-save>儲存鑰匙</button></div>`}</div>
    <div class="set-group"><h3>備份與還原</h3><div class="btn-row"><button type="button" class="btn sm" data-backup>複製備份碼</button><button type="button" class="btn sm" data-restore>貼上備份碼</button></div></div>
    <div class="set-group"><h3>資料來源狀態</h3>${healthHtml()}</div>`);
}
function healthHtml() {
  const H = S.d.meta?.health || {};
  const P = H.patches || {};
  const names = S.d.meta?.sources || {};
  const rows = Object.entries(P).map(([k, v]) => `<span>${esc(names[k]?.p || k)}</span><span class="${v.ok ? 'ok' : 'bad'}">${v.ok ? `${v.n} 則` : `讀不到${v.last_ok ? `（用 ${md(v.last_ok)} 的資料）` : ''}`}</span>`);
  const pr = H.prices || {};
  for (const v of ['claude', 'chatgpt', 'gemini', 'grok']) if (pr[`parse_${v}`]) rows.push(`<span>${VNAME[v]} 價格表</span><span class="${String(pr[`parse_${v}`]).startsWith('ok') ? 'ok' : 'bad'}">${String(pr[`parse_${v}`]).startsWith('ok') ? '正常' : '讀不到，沿用上次'}</span>`);
  const tr = S.d.meta?.translate || {};
  rows.push(`<span>中文翻譯</span><span class="${tr.ok ? 'ok' : 'bad'}">${tr.ok ? `本輪翻 ${tr.done || 0} 則` : '翻譯器沒啟動'}${tr.pending ? `，${tr.pending} 則排隊` : ''}</span>`);
  return `<div class="health">${rows.join('')}</div>`;
}

// ------------------------------------------------------------------ 找 Claude 討論
function askClaude(text) {
  const done = () => toast('已複製，貼到 Claude 就能討論');
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(done).catch(() => toast('複製失敗，請手動選取'));
  const url = text.length < 1800 ? `https://claude.ai/new?q=${encodeURIComponent(text)}` : 'https://claude.ai/new';
  window.open(url, '_blank', 'noopener');
}
function askPatch(id) {
  const x = (S.d.patches?.items || []).find((i) => i.id === id);
  if (!x) return;
  const p = prefs();
  askClaude(`我在《版本答案》看到這則 AI 改版，想聽你的看法：這對我有什麼影響、要不要改變做法？\n\n【${VNAME[x.v]}．${x.p}】${x.d}\n${x.tz || ''}\n${x.sz || ''}\n原文：${x.t}\n${(x.b || '').slice(0, 600)}\n${x.url || ''}\n\n我的方案：Claude ${p.tiers.claude}、ChatGPT ${p.tiers.chatgpt}、Gemini ${p.tiers.gemini}、Grok ${p.tiers.grok}；筆電 RTX 5090 Laptop 24GB、64GB RAM。`);
}
function askTask(id) {
  const t = (S.d.guide?.tasks || []).find((x) => x.id === id);
  if (!t) return;
  askClaude(`請幫我重新評估《版本答案》裡「${t.name}」的版本答案還對不對，要不要改。\n\n目前答案：\n${(t.picks || []).map((p) => `${p.rank}：${p.tool || ''} ${p.model || ''}—${p.why || ''}`).join('\n')}\n\n系統標出的變動：\n${(t.flags || []).map((f) => `- ${f.text}${f.items ? '：' + f.items.map((i) => i.t).join('；') : ''}`).join('\n') || '（沒有）'}\n\n請先上網查最新狀況再回答；確定要改的話，告訴我 config/playbook.json 要怎麼改。`);
}
function askModel(id) {
  const m = [...(S.d.local?.llm || []), ...(S.d.local?.diffusion || [])].find((x) => x.id === id);
  if (!m) return;
  const f = m.kind ? diffFit(m) : llmFit(m);
  askClaude(`我想在筆電上跑 ${m.name}（${m.hf || ''}）。筆電是 RTX 5090 Laptop 24GB、64GB RAM、Windows。《版本答案》估算：${f ? `${LV[f.level]}，需要約 ${f.need.toFixed(1)} GB` : '還沒有數字'}。請告訴我最適合的安裝方式、設定，以及拿來做我的工作（寫小說、做遊戲、做影片）實際好不好用。`);
}

// ------------------------------------------------------------------ 更新（遙控鑰匙）
async function gh(path, opt = {}) {
  const key = lsGet(KEY_KEY);
  return fetch(`https://api.github.com${path}`, { ...opt, headers: { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', ...(key ? { Authorization: `Bearer ${key}` } : {}), ...(opt.headers || {}) } });
}
async function onScan() {
  if (S.scanning) return;
  const btn = $('#scan');
  const key = lsGet(KEY_KEY);
  btn.classList.add('busy');
  let changed = false;
  try { changed = await loadData(true); } catch (e) { toast(e.message); }
  liveStatus();
  if (changed || !key) {
    btn.classList.remove('busy');
    renderAll();
    toast(changed ? `已更新到 ${hm(S.d.meta.generated)} 的資料` : `已經是最新（${ago(S.d.meta.generated)}）。每小時自動更新；設定遙控鑰匙可以立刻重抓。`);
    return;
  }
  S.scanning = true;
  const repo = S.d.meta.repo;
  const started = Date.now();
  toast('已請 GitHub 重抓，大約 5 分鐘');
  try {
    const r = await gh(`/repos/${repo}/actions/workflows/meta.yml/dispatches`, { method: 'POST', body: JSON.stringify({ ref: 'main', inputs: { mode: 'build' } }) });
    if (r.status === 401 || r.status === 403) throw new Error('鑰匙沒有權限或已過期，到「我的設定」重新設定。');
    if (r.status !== 204) throw new Error(`GitHub 回應 ${r.status}，請稍後再試。`);
    let run = null;
    for (let i = 0; i < 80; i++) {
      await new Promise((ok) => setTimeout(ok, i < 3 ? 4000 : 8000));
      const rr = await gh(`/repos/${repo}/actions/runs?event=workflow_dispatch&per_page=5`);
      if (!rr.ok) continue;
      const js = await rr.json();
      run = (js.workflow_runs || []).find((x) => new Date(x.created_at).getTime() >= started - 60000) || run;
      if (run && run.status === 'completed') break;
    }
    if (!run || run.conclusion !== 'success') throw new Error('這輪更新沒有完成，等一下再試。');
    const before = S.d.meta.generated;
    for (let i = 0; i < 24; i++) {
      await new Promise((ok) => setTimeout(ok, 8000));
      try { await loadData(true); } catch (e) { continue; }
      if (S.d.meta.generated !== before) break;
    }
    renderAll();
    toast(`已更新到 ${hm(S.d.meta.generated)} 的資料`);
  } catch (e) {
    toast(e.message);
  } finally {
    S.scanning = false;
    btn.classList.remove('busy');
  }
}

// 伺服器狀態：打開 App 時直接問官方狀態頁（Claude、OpenAI、xAI 允許網頁直接讀）
async function liveStatus() {
  const get = (u) => fetch(u, { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const lvl = { none: 'ok', minor: 'minor', major: 'major', critical: 'critical', maintenance: 'minor' };
  const [c, o, x] = await Promise.all([get('https://status.claude.com/api/v2/summary.json'), get('https://status.openai.com/api/v2/summary.json'), get('https://data.x.ai/status/incidents.json')]);
  const base = S.d.status?.vendors || {};
  const merge = (v, s) => {
    if (!s) return;
    const act = (s.incidents || []).filter((i) => !['resolved', 'postmortem'].includes(i.status));
    let ind = lvl[s.status?.indicator] || 'ok';
    if (act.length && ind === 'ok') ind = 'minor';
    S.live[v] = { ...(base[v] || {}), ind, active: act.map((i) => ({ t: i.name, impact: lvl[i.impact] || 'minor' })) };
  };
  merge('claude', c);
  merge('chatgpt', o);
  if (x) {
    const act = (x.incidents || []).filter((i) => !['resolved', 'postmortem'].includes(i.status));
    S.live.grok = { ...(base.grok || {}), ind: act.length ? (lvl[act[0].impact] || 'minor') : 'ok', active: act.map((i) => ({ t: i.name, impact: lvl[i.impact] || 'minor' })) };
  }
  const el = $('.servers');
  if (el && S.view === 'home') el.outerHTML = serversHtml();
}

// ------------------------------------------------------------------ 路由與事件
function footHtml() {
  const M = S.d.meta;
  return `<p class="foot">資料 ${esc(hm(M.generated))} 更新．每小時自動更新一次。只用官方頁面與公開資料，不收業配與導購連結。<br>
  <button type="button" class="linkbtn" data-sheet="settings">資料來源狀態與設定</button></p>`;
}
function renderAll() {
  const M = S.d.meta;
  if (!M) return;
  const old = Date.now() - new Date(M.generated).getTime() > 3 * 3600000;
  $('#fresh').innerHTML = `<span class="dot${old ? ' warn' : ''}"></span>${esc(ago(M.generated))}更新`;
  const map = { home: renderHome, patch: renderPatch, shop: renderShop, local: renderLocal, guide: renderGuide };
  try { map[S.view](); } catch (e) { console.error(e); $(`#v-${S.view}`).innerHTML = `<div class="empty">這一頁顯示時出錯：${esc(e.message)}</div>`; }
}
function route() {
  const h = location.hash.replace(/^#\/?/, '').split('?')[0] || 'home';
  S.view = ['home', 'patch', 'shop', 'local', 'guide'].includes(h) ? h : 'home';
  $$('.view').forEach((v) => { v.hidden = v.dataset.view !== S.view; });
  $$('.tabs a').forEach((a) => { if (a.dataset.tab === S.view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  renderAll();
  window.scrollTo(0, 0);
}
let toastT;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => { t.hidden = true; }, 3200);
}
document.addEventListener('click', (ev) => {
  const el = ev.target.closest('button, [data-pid], [data-lm], [data-dm], a');
  if (!el) return;
  const d = el.dataset;
  if (d.close !== undefined || ev.target.matches('.sheet-back')) { closeSheet(); return; }
  if (el.id === 'scan') { onScan(); return; }
  if (el.id === 'gear' || d.sheet === 'settings') { settingsSheet(); return; }
  if (d.sheet === 'allmodels') { allModelsSheet(); return; }
  if (d.srv) { serverSheet(d.srv); return; }
  if (d.pm) { S.pm = d.pm; if (location.hash.includes('?')) location.hash = '#/patch'; else renderPatch(); return; }
  if (d.pv) { S.pv = d.pv; renderPatch(); return; }
  if (d.askPatch) { askPatch(d.askPatch); return; }
  if (d.askTask) { askTask(d.askTask); return; }
  if (d.askModel) { askModel(d.askModel); return; }
  if (d.shopv) { S.shopV = d.shopv; renderShop(); return; }
  if (d.shopvGo) { S.shopV = d.shopvGo; closeSheet(); location.hash = '#/shop'; return; }
  if (d.verdict) { verdictSheet(d.verdict); return; }
  if (d.lcat) { S.lcat = d.lcat; renderLocal(); return; }
  if (d.kvq) { prefs().kvq = d.kvq; savePrefs(); renderLocal(); return; }
  if (d.lmq) { prefs().quant[d.lmq] = d.q; savePrefs(); llmSheet(d.lmq, d.q); if (S.view === 'local') renderLocal(); return; }
  if (d.dm2) { diffSheet(d.dm2, +d.dmv); return; }
  if (d.copy) { navigator.clipboard?.writeText(d.copy).then(() => toast('已複製')); return; }
  if (d.keySave !== undefined) { const v = $('#key-in').value.trim(); if (!v.startsWith('github_pat_') && !v.startsWith('ghp_')) { toast('這不像 GitHub 鑰匙，請再確認'); return; } lsSet(KEY_KEY, v); toast('已儲存，之後按「更新」會直接叫 GitHub 重抓'); settingsSheet(); return; }
  if (d.keyDel !== undefined) { lsSet(KEY_KEY, null); toast('已移除'); settingsSheet(); return; }
  if (d.backup !== undefined) { const code = btoa(unescape(encodeURIComponent(JSON.stringify(prefs())))); navigator.clipboard?.writeText(code).then(() => toast('備份碼已複製')); return; }
  if (d.restore !== undefined) { const code = prompt('貼上備份碼'); if (!code) return; try { S.prefs = { ...defaults(), ...JSON.parse(decodeURIComponent(escape(atob(code.trim())))) }; savePrefs(); applyTheme(); toast('已還原'); settingsSheet(); renderAll(); } catch (e) { toast('備份碼不正確'); } return; }
  if (d.pid && !ev.target.closest('a, button')) { if (S.open.has(d.pid)) S.open.delete(d.pid); else S.open.add(d.pid); el.classList.toggle('open'); el.setAttribute('aria-expanded', el.classList.contains('open')); return; }
  if (d.lm && !ev.target.closest('a')) { llmSheet(d.lm); return; }
  if (d.dm && !ev.target.closest('a')) { diffSheet(d.dm); return; }
});
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && !$('#sheet').hidden) closeSheet();
  if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.matches('[data-pid], [data-lm], [data-dm]')) { ev.preventDefault(); ev.target.click(); }
});
document.addEventListener('change', (ev) => {
  const el = ev.target;
  const d = el.dataset;
  const p = prefs();
  if (d.pref === 'tier') { p.tiers[d.v] = el.value; }
  else if (d.pref === 'hits') { p.hits[d.v] = el.value; }
  else if (d.pref === 'use') { const set = new Set(p.uses[d.v] || []); if (el.checked) set.add(el.value); else set.delete(el.value); p.uses[d.v] = [...set]; }
  else if (d.pref === 'theme') { p.theme = el.value; applyTheme(); }
  else if (d.calc) { S.calc[d.calc] = d.calc === 'id' ? el.value : Math.max(0, +el.value || 0); renderShop(); return; }
  else return;
  savePrefs();
  if (d.pref === 'tier') settingsSheet();
  renderAll();
});
document.addEventListener('input', (ev) => {
  if (ev.target.dataset.knob === 'ctx') {
    const ctxs = [4096, 8192, 16384, 32768, 65536, 131072];
    prefs().ctx = ctxs[+ev.target.value] || 32768;
    savePrefs();
    clearTimeout(S.knobT);
    S.knobT = setTimeout(renderLocal, 60);
  }
});
window.addEventListener('hashchange', route);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && S.d.meta && Date.now() - new Date(S.d.meta.generated).getTime() > 75 * 60000) {
    loadData(false).then((ch) => { if (ch) renderAll(); }).catch(() => {});
    liveStatus();
  }
});

(async function boot() {
  applyTheme();
  $$('.view').forEach((v) => { v.innerHTML = '<div class="skel"></div>'; });
  try {
    await loadData(false);
  } catch (e) {
    $('#v-home').innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  S.prefs = null;
  prefs();
  applyTheme();
  route();
  liveStatus();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
})();
