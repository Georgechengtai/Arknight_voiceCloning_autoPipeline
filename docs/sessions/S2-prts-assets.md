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
- PRTS 會重置連線：每請求間隔 ≥ 1 s，指數退避重試 3 次，`User-Agent` 只寫專案名，不含任何個人資料（2026-10-05 專案擁有者決定；原文曾要求寫聯絡方式）。

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
2026-10-05，worktree `elastic-keller-870d42`（任務書寫的 `assets` worktree 以實際所在目錄為準）。

**做了什麼**
- `pipeline/assets.py`＋命令 `python -m pipeline assets --scene <場景>`（省略 `--scene` 就是整個活動；`--dry-run` 只解析不下載，再加 `--verify` 會逐一連線確認檔案存在）。單測 `tests/test_assets.py` 26 個，全套 61 個通過。
- **BB-ST-1 素材 100% 到位**：背景 4、插圖 2、立繪 21（8 組）、音樂 6、音效 12，共 45 個檔，`missing` 為空；每個檔都用 ffmpeg 完整解碼過一次，無錯誤。清單在 `out/act33side_st01/assets_manifest.json`（沒有動該目錄任何既有檔案）。
- 指定要確認的音訊鍵全部抓到：`Mon3tr_n`（1.18 秒）、`char_Mon3tr`（3.08 秒）、`p_skill_Mon3trburst`（4.23 秒）、`drift_intro/loop`、`loneliness_intro/loop`、`act18d0d0_intro/loop`。
- **全 23 場 dry-run（逐一連線確認）**：背景 62/62、插圖 30/30、立繪 199/199、音樂 72/72、音效 150/150，解析不到 0 項。報告在 `out/reports/assets_dryrun_act33side.json`。只下載了 BB-ST-1，其餘 22 場沒有下載。
  - 背景是 62 而不是文件寫的 48：多出來的是過場遮罩 `interlude` 露出的背景 2 張，與 `gridbg` 長卷的 12 張分片（3 組各 4 張）。
  - 4 張 `gridbg` 分片（`38_g20_skyblue_r1/r2`、`38_g21_skystarry_r1/r2`）fexli 沒有，由 PRTS 備援命中。其餘圖全在 fexli，音訊全在 PRTS，沒有用到 Aceship。

**實測得到的規則（已寫回 `docs/02-data-sources.md` 檔尾）**
- 音訊網址必須**整條小寫**：`https://torappu.prts.wiki/assets/audio/music/act9d0d0/m_avg_drift_intro.mp3`。保留索引原本的大小寫（`Music`、`Mon3tr`）一律 404。
- torappu 同一路徑也有 `.wav`，但實測下載極慢（4 MB 抓了數分鐘沒抓完），沒有採用；音樂、音效一律 MP3（44.1 kHz 立體聲 128 kbps）。
- media.prts.wiki 的圖片網址可直接下載；網址裡的 `$` 要跳脫成 `%24`。

**偏離任務書之處**
- 沒有用 requests，沿用專案既有的 urllib＋certifi（不加新依賴）。
- manifest 比任務書的範例多了欄位：每筆有 `source`、`bytes`，圖片有 `w`/`h`，音訊有 `dur`（秒）與 `index_path`；頂層多 `scene_id`、`effects`、`warnings`。`missing` 的每一項是 `{kind, key, reason}`。立繪的 `variants` 以**腳本裡的完整名字**為鍵（例 `avg_003_kalts_1#4$1`），渲染器拿 charslot 的 `name` 直接查。契約寫在 `docs/01-architecture.md` 檔尾。
- 音效檔放 `assets/audio/sound/`，音樂放 `assets/audio/music/`；每個檔的來源另記在 `assets/sources.json`（重跑時檔案已存在不會再下載，來源從這裡讀）。
- 索引快取放 `cache/prts/`、`cache/fexli/`（worktree 內、不入庫；合回主倉庫後第一次執行會重抓五個索引檔）。
- **User-Agent 只寫專案名，不含任何聯絡方式**（專案擁有者決定）。任務書原文要求寫聯絡方式；我一開始未經詢問填了他的信箱並已送出若干請求，事後詢問時他明確要求改掉，並要求個人資料對外一律先徵得同意。現已移除，設定檔與所有產出檔裡都沒有信箱。

**留給渲染器（S5）與整合（S6）的事**
- 舊背景的原始解析度只有 1024×576（BB-ST-1 的 4 張背景與 `avg_5_7_shining` 都是；PRTS 上同樣大小，這是遊戲原檔），放大到 1920×1080 會偏軟。`49_i01` 是 1600×900。
- 立繪圖檔的像素尺寸（1024、1280、1328 見方）與清單裡的 `size`（遊戲座標系下的顯示尺寸，如 890）不同，渲染時要以 `size` 縮放、以 `pos` 定位。
- 立繪每個表情都是完整的一張圖（不是只有臉的貼片），不必自己合成。
- MP3 開頭有約 25 毫秒的編碼延遲，intro 接 loop、loop 自我循環時若聽得到接縫，要在混音時裁掉頭尾的填充。
- `effects`（粒子、下雪、老電視等 23 種，BB-ST-1 一個都沒用到）沒有可下載的檔，要由渲染器自己實作或略過；清單列在 dry-run 報告。
- **彩蛋音效候選**（只記錄，未下載）：Mon3tr 另有 `b_char_mon3terdieroar_phase0`、`b_char_mon3terdieroar_phase2`（咆哮）；「未知語言」可考慮 `d_avg_spiritwhisper`、`d_avg_darkwhisper`、`d_avg_ghostwhisper`（低語類）。BB-ST-2 的未知語言台詞實際有 44 句（多數是「？？？」），腳本在其中幾句旁邊本來就排了 `d_avg_labamb`、`d_avg_scan`。

## 補充 2026-10-05（開工前必讀）
- 在 worktree `.claude/worktrees/assets` 工作。worktree 裡的 `out`、`data`、`assets`、`.venv` 都是連到主倉庫的捷徑（不入庫），所以 `out/act33side_st01/timeline.json` 已經在；下載的素材直接落在主倉庫的 `assets/`，其他 session 也看得到。
- timeline 的實際格式以 `pipeline/schemas/timeline.schema.json` 與 `docs/01-architecture.md` 的兩節追加為準。
- BB-ST-1 會用到的指令數量：charslot 103、blocker 41、playsound 18、background 4、image 4、playmusic 3，另有 backgroundtween、imagetween 各 1。
- 這一輪的目標是「第一支完整影片」：BB-ST-1 的素材 100% 到位優先，全 23 場的 dry-run 其次。
- 專案擁有者提過 Mon3tr 的叫聲、未知語言的台詞可以用音效當彩蛋：如果素材索引裡找得到對應的音效請記在完成記錄裡，不必下載。
