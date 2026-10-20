# 版本答案 META — 給接手的 Claude

使用者 PZ（痞子葳）沒有程式背景，所有回覆用繁體中文、白話。這個 repo 是他的 AI 工具雷達 App（繼《冷眼》《玩真的》《回波》《下單前》之後的資訊 App）。主力是 Claude（Max 5x），另有 ChatGPT Plus（實付 NT$699）、Gemini 免費版、Grok 免費版；筆電是 ROG Strix SCAR 18（RTX 5090 Laptop GPU 24 GB、64 GB DDR5-5600）。

## 原則（不可違反）
- PZ 說「開工」才動手；討論階段不做任何檔案或改動。
- 只用官方頁面與公開資料；不收業配、不放導購連結。
- 分類、分數、判定一律是固定規則，同樣的資料得到同樣的結果，並附「為什麼」。
- 「額度雷達」（個人用量監控）PZ 決定先不做；不要擅自加。
- 鑰匙（GitHub token）只存在使用者裝置的 localStorage，絕不寫進 repo 或資料檔。

## 怎麼運作
- `.github/workflows/meta.yml` 每小時第 13 分跑 `pipeline/dispatch.py` → `build.py`。推到 `main` 時執行 `control/job.json` 指定的工作：`build`／`deploy`（只改介面）／`probe`（實測新來源，原始回應存到 `probe-results` 分支，清單在 `control/probe.json`）。
- 雲端 Claude 工作環境連不到這些網站（只連得到 GitHub），要實測就用 `probe`。
- 改版：`feeds.py`（各家更新紀錄的解析器）→ `patches.py`（分類加強／削弱／新增／移除／調整／修正、標籤、「跟你有關」分數、合併、每天發版的工具一週併一則）→ `translate.py`（Actions 裡的 llama.cpp＋Qwen3-8B 翻成台灣用語，快取在 state）。
- 價格：`prices.py` 讀 Claude／Gemini／xAI 的 markdown 文件與 OpenAI 價格頁，OpenRouter 交叉核對；記錄漲降價歷史與「即將發生」。
- 狀態：`status.py`（Claude、OpenAI 的 Statuspage JSON；xAI 自己的狀態 JSON；Google Cloud 事故裡跟 Gemini 有關的）。App 也會直接向 Claude、OpenAI、xAI 的狀態頁即時確認。
- 方案：`config/plans.json`（人工整理，每格附官方來源）＋ `plans.py`（匯率、官方方案頁變動偵測：連續兩輪一樣才算變動、iOS App 版本）。Google 在台灣用台幣計價（`twd_official`）。
- 本機：`config/local.json`（精選清單，人工挑）＋ `local.py`（每天從 Hugging Face 讀 GGUF 檔案大小與 config.json 架構、新上架雷達、工具最新版）＋ `vram.py`（吃多少顯示記憶體、多快）。
- 攻略：`config/playbook.json`（人工）＋ `guide.py`（模型停用、同家族出新版、精選清單移除、相關改版、45 天沒複查 → 亮燈）。
- 跨輪資料在 `state` 分支（改版快取、翻譯快取、價格歷史、HF 快取、方案頁指紋），每次只留一個 commit；`out/` 是最近一次輸出，`runs.json`、`health.json`、`diag/` 是執行紀錄與各來源狀態。

## 容易改壞的規則
- 「跑得動嗎」：`pipeline/vram.py` 跟 `site/app.js` 的 `vramPlan`／`speedOf`／`kvGib` 必須一模一樣（App 拉對話長度時在手機上重算）。改一邊就跑 `python3 tests/check_vram.py`。
- 速度公式用公開實測校準（Muse Glimmer 官方桌機 5090 數據、4090 的 32B 與 Qwen3-30B-A3B 實測），常數改之前先想清楚。
- GGUF 檔案大小：`local.quant_sizes` 只算主模型，排除 mmproj、MTP、DFlash 草稿檔；子資料夾只認以壓縮等級命名的。同一倉庫放多個模型時用 `gguf_stem`。
- 架構：Gemma 4 的全域層用 `global_head_dim`／`num_global_key_value_heads`（存在 `kv_bpt`）；Qwen3.5 系列是線性注意力混合（只有 1/4 層存對話記憶）；Nemotron-H 用 `layers_block_type`。
- 訂閱判定的「用途重疊」看的是使用者勾的用途（實際拿哪家做），不是方案理論上做得到；不然主力 Claude 會被建議砍掉。
- 方案 id（`max5`、`pro100`…）對到公告裡的方案家族（`patches.TIER_FAMILY`），`config/rules.json` 的 `plan_words` 用家族名。
- 新聞稿（公司、政策、客戶故事）分數上限 5 分，不進「跟你有關」。

## 本機測試
- 把 `probe-results` 分支解開到 scratchpad（每一批各一個資料夾），`PROBE=<新的>:<舊的> python3 tests/local_build.py <輸出資料夾> <state 資料夾>` 用原始回應跑一整輪（不連網）。
- 介面：起本機伺服器開輸出資料夾，用 Playwright 以手機寬度（390×844）截深色、淺色圖檢查，並看主控台有沒有錯誤。

## 介面
- 主題：遊戲改版公告 × 段位表。深靛藍底、TierMaker 式段位色、施工膠帶條紋；招牌是首頁巨大的週改版號（例如 26.43）。
- 純 HTML／CSS／JS，沒有外部程式庫；數字用 Chakra Petch（Google Fonts），中文用系統字。PWA：`sw.js` 快取外殼，資料一律先抓網路。
