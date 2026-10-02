# S2 素材解析與下載器（fexli 首選、PRTS 備援）

## 目標
`python -m pipeline assets --scene act33side_st01` 讀 timeline.json，解析每個背景、插圖、立繪變體、BGM、音效的 URL，限速下載到 `assets/`，輸出 `out/<scene>/assets_manifest.json`（事件→本地檔路徑）。對 BB-ST-1 做到 100% 命中。

## 來源優先序（2026-10-02 更新，詳見 docs/02-data-sources.md §3–3d）
- 背景 / CG / 立繪：**先 fexli/ArknightsResource**（raw.githubusercontent，規則見 §3b；立繪變體用 `avgs/npcs/summary.json`），404 再退 PRTS 索引。
- BGM / 音效：先 PRTS Data_Audio → torappu.prts.wiki（URL 規則待實測），失敗退 Aceship/Arknight-voices WAV（§3c，150/222）。兩者都沒有的鍵寫入 `missing` 並讓渲染靜音該音效。
- 每個素材在 manifest 中記錄實際來源 `source: fexli|prts|aceship`。

## 已知事實（詳見 docs/02-data-sources.md §3）
- 索引：`https://prts.wiki/index.php?title=Widget:Data_Image&action=raw`（同理 Data_Char、Data_Link、Data_Audio）。快取到 `cache/prts/`，24 h 內不重抓。
- 背景鍵 = `bg_` + image 名；Image() 插圖鍵 = 原名。
- 立繪：先 `Data_Link[group]`（找不到試 `group + "_1"`），在 `array[].name` 中找 `group-<face>$<body>`；face 缺省取 1，body 缺省取 1；找不到精確變體就退到 array[0] 並記 warning。再用該 name 查 Data_Char 得 URL。保存 Data_Link 的 pos/size 到 manifest（S5 需要）。
- 音訊：`https://torappu.prts.wiki/assets/` + `Data_Audio[key]`.lower().replace("sound_beta_2","audio") + `.mp3`。**此 URL 推自播放器原碼未實測**：先用 BB-ST-1 的 `drift_intro` 測大小寫兩種形式，把實際可用規則寫回 `docs/02-data-sources.md`。
- PRTS 會重置連線：每請求間隔 ≥ 1 s，指數退避重試 3 次，`User-Agent` 寫明專案名與聯絡方式。

## 步驟
1. `pipeline/assets.py`：索引載入（含快取）、鍵解析函式（純函式，可單測）、下載器（requests + 重試 + 限速 + 已存在跳過）。
2. 對 BB-ST-1 跑通；再對全 23 場只跑「解析不下載」(`--dry-run`) 驗證 48/48、199/199、全部音訊鍵。
3. 寫 `assets_manifest.json`：
   ```json
   {"backgrounds": {"bg_laccolith": {"url": "...", "path": "assets/bg/bg_laccolith.png"}},
    "images": {...},
    "sprites": {"avg_npc_053": {"pos": {"x":0,"y":180}, "size": {"x":1024,"y":1024}, "variants": {"avg_npc_053": {"url": "...", "path": "assets/char/avg_npc_053.png"}}}},
    "music": {"drift_intro": {"url": "...", "path": "assets/audio/music/drift_intro.mp3"}},
    "sounds": {...},
    "missing": []}
   ```
4. 單測：鍵解析函式對 `docs/02-data-sources.md` 列的各種鍵形式。

## 驗收
- BB-ST-1：`missing` 為空；所有檔案存在且 PNG/MP3 可被 Pillow / ffprobe 打開。
- 全巴別塔 dry-run：missing 為空或每一項都有解釋。

## 邊界
- 只下載 timeline 需要的素材，不鏡像整個索引。
- 不抓 HTML 頁；不碰 PRTS 的 StoryPlayer bundle。

## 完成記錄
（session 結束時填寫）
