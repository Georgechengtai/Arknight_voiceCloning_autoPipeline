# S5 HTML/Canvas 渲染器、Playwright 逐幀截圖、ffmpeg 合成

## 目標
`python -m pipeline render --scene act33side_st01` 讀 timeline.json、assets_manifest.json、audio/ 下 WAV 的時長，產出 1920×1080、30 fps 的 `out/<scene>/<scene>.mp4`（語音＋BGM＋音效三軌混音），以及 `--no-bgm` 變體。

## 設計要點（詳見 docs/01-architecture.md「渲染器約定」）
1. 時間軸展開：Python 端先把事件序列轉成**絕對時間表** `schedule.json`：每個事件的開始時刻、每個 line 的顯示區間（= 音訊長度 + 0.5 s；無音訊按字數），blocker/sticker/delay 照腳本；輸出總長度。渲染器只消費 schedule，不自己算節奏。
2. 渲染器 `pipeline/render/web/index.html`：Canvas 2D；載入 schedule 與素材路徑（Playwright 用 `file://` 或本地 http.server）；暴露 `window.renderer.ready` Promise 與 `window.renderer.seek(t_ms)`（同步繪製該時刻畫面，確定性，不用 rAF）。
   - 圖層順序：背景 → 立繪（l/m/r 槽，Data_Link pos/size 換算到 1280×720 再 ×1.5；錨點語義參照 PRTS ScenarioSimulator 的 `case "l"/"m"/"r"` 分支，取回 `https://prts.wiki/index.php?title=Widget:ScenarioSimulator&action=raw` 對照）→ Image 插圖 → Sticker → Blocker 色塊 → 對話框（名字＋文字，打字機：每字 30 ms，於音訊開始時同步）→ Subtitle。
   - 立繪變化：帶 duration 的 charslot 做淡入；說話者立繪略亮、非說話者 85% 亮度（近似遊戲）。CameraShake 以正弦位移近似。
   - 字體 Noto Sans CJK SC（本地安裝或 assets/fonts/）。
3. Playwright（Python）：headless Chromium，viewport 1920×1080，`device_scale_factor=1`；對 t = 0, 1/30, 2/30 … 呼叫 seek 後 `page.screenshot()`；用 `ffmpeg -f image2pipe -framerate 30 -i -` 從 stdin 編碼，避免落地幾千張 PNG（可選 `--keep-frames` 除錯）。
4. 音訊：ffmpeg filter_complex：語音軌按 schedule 的 line 起點 `adelay`；BGM 軌 intro→loop（`aloop` 或預先拼到足夠長）按 playmusic/stopmusic 區間裁切與 `afade`；音效軌按 playsound/stopsound/soundvolume；三軌 `amix` 前先各自輸出 `voice.wav`、`bgm.wav`、`sfx.wav` 便於除錯與 `--no-bgm`。
5. 效能目標：BB-ST-1（約 8–10 分鐘影片）在 M 系列 Mac 上 ≤ 60 分鐘渲染。若 screenshot 太慢，改成在頁內用 `canvas.toDataURL`/`toBlob` 批量回傳或 WebCodecs 編碼——先量測再優化。
6. 單測：schedule 展開（給定音訊長度表，檢查每事件時刻）；渲染器以 Playwright 在 3 個時刻截圖與基準圖做像素差（容忍 1%）。

## 開源參考
- `https://raw.githubusercontent.com/akgcc/akgcc.github.io/master/js/story.js`（MIT）：60 多個指令的解析與語義，特別是 charslot/character 的 slot 與 focus 映射（`CharslotNameMap`、`CharslotFocusMap`）、sticker/subtitle、blocker、camerashake、imagetween。它是滾動閱讀器，只借語義不借 DOM 結構。
- PRTS `Widget:ScenarioSimulator`（只讀）：全屏座標語義。
- 互動播放模式是專案後話，不在本 session 範圍。

## 在 S4 完成前如何開發
用 macOS `say -v Tingting` 或任意 TTS 生成佔位 WAV（檔名按 line_id），只為拿到時長；不要把佔位音訊入庫。

## 驗收
- BB-ST-1 MP4 可播放，音畫同步（抽 5 句人工看字幕與語音起點差 < 100 ms）。
- `--no-bgm` 版本生成。
- 渲染器 `seek` 對同一 t 兩次截圖逐像素相同。

## 邊界
- 不實作互動模式（點擊推進）——但不要寫死到妨礙日後加上。
- 不做 Effect / bgeffect / ImageTween 的精確還原；以淡入淡出近似並在 schedule 標記 `approx: true`。

## 完成記錄
2026-10-05，在 worktree `affectionate-saha-c29c07` 完成（不是原定的 `renderer`，照專案擁有者指示以當時所在目錄為準）。契約與節奏的細節寫在 `docs/01-architecture.md` 最後一節「追加 2026-10-05（S5 渲染器實作後…）」，這裡只記做了什麼與留下的問題。

### 做了什麼
- `pipeline/render/schedule.py`：timeline＋語音清單＋素材清單 → 絕對時間表（純函式）。
- `pipeline/render/web/`：`index.html`＋`renderer.js`，Canvas 2D，`renderer.load(schedule)`、`renderer.seek(毫秒)`；另有給人看的預覽模式（拖曳條＋播放）。
- `pipeline/render/frames.py`：本機網站＋Playwright 逐幀截圖，直接餵 ffmpeg 編碼；可用 `--workers` 分段同時畫。
- `pipeline/render/audio.py`：語音、音樂、音效三軌各自成檔，再混成有音樂、無音樂兩版。
- `pipeline/render/placeholder.py`：佔位語音清單（`say` 或靜音），格式與正式清單相同。
- 指令 `render`、`render-placeholder`、`render-preview`；設定在 `config/settings.yaml` 的 `render` 一節（間隔、版面、音量、片頭字卡的文字都可調）。
- 測試 26 個（全套 61 個全過）：時間表 16、音軌 4、渲染器頁面 6（同一刻畫兩次逐位元組相同；三個時刻與 `tests/baseline/` 的基準圖比對）。基準圖是色塊佔位畫面，不含遊戲素材，已在 `.gitignore` 開例外。

### BB-ST-1 的結果
- 開工時另外兩個 session 的清單還沒出來，中途都出來了，所以成品用的是**正式的語音清單與素材清單**：`out/act33side_st01/act33side_st01.mp4`（有音樂）與 `act33side_st01_nobgm.mp4`，1920×1080、30 fps、12 分 26 秒、約 100 MB。素材沒有缺漏，時間表沒有警告。
- 佔位清單也照任務書生了一份（`out/act33side_st01/placeholder/`，143 句用 `say` 念），只用它算過時間表（`render-placeholder/schedule.json`），沒有出片。
- 用時：單一瀏覽器 25 分 43 秒（目標 60 分鐘內）。22395 幀裡只有 6705 幀畫面有變化、需要截圖；慢的是背景與插圖緩慢縮放的那幾段，以及 H.264 編碼（當時機器上還有別的 session 在跑）。
- 驗收：五句（0022、0050、0064、0090、0126）語音在成品裡的位置與時間表相差 0–10 毫秒，字都在排定的那一幀出現；同一時刻截圖兩次逐位元組相同；無音樂版已生成。
- 沒有刪除或覆蓋 `out/act33side_st01/` 原有的任何檔案；新增的是 `render/`、`render-placeholder/`、`placeholder/` 三個目錄與兩支影片。

### 與任務書不同之處
- 間隔的放法、字卡在黑幕之上、壓暗亮度 0.6：理由見架構文件。
- 沒有先把每一幀存成圖檔比對，改為「畫面狀態相同就不重畫」；`--keep-frames` 仍可把每一幀另存。
- Playwright 沒能用 pip 裝進專案環境（當天下載套件的網路一直卡住），改把這台 Mac 系統 Python 裡已有的 1.59.0 版複製進 `.venv`（同一個 Python 3.11）。`pyproject.toml` 已加上 `render` 這組選用套件；換機器時照常 `pip install -e ".[render]"` 再 `python -m playwright install chromium` 即可。
- 片頭字卡（`--intro-card`）已實作並有測試，預設文字「本片语音为 AI 生成」、4 秒；這次的成品沒有加，留給整合階段決定最終文字後一起出。

### 專案擁有者看過第一版後（同日）
- 音量「大差不差，可以了」，`bgm_gain_db`、`sfx_gain_db` 維持預設。
- PRTS 連得上了：立繪左右位置改成原始碼裡的數字（畫面寬度的 34%／50%／66%，原先猜的 25%／75% 太靠兩邊），打亮規則也對齊，細節見架構文件。
- 照他的意思裝了 Noto Sans CJK SC 字型，基準圖已重新產生。
- 以上改完後重出一版；第一版影片沒有刪，檔名後面加了日期時間留在同一個目錄。
- 他對配音提了三點（結局句末字、結尾「那么……」、旁白棒讀），原因與建議做法記在 `docs/00-decisions.md` 檔尾，交給配音的 session 處理，這裡沒有動配音。

### 第三版（2026-10-06 凌晨）：混音修正＋配音更新
應主 session（BB-ST-1 配音）的要求做的兩件事，結果在 `out/act33side_st01/act33side_st01.mp4`（前兩版都改名留著）：
- **音樂在有人說話時自動退後**（新功能，`render.audio.duck`）：固定降 12 dB 之外，說話時再退 6 dB；開口前 0.25 秒開始退、說完 0.6 秒內回來、兩句相隔不到 1.5 秒不回升。做法是依時間表的語音時段畫音量線，不是即時聽音量壓。
- **實測（只量有人說話的時段）**：語音 −18.6 LUFS、音樂 −38.4 LUFS，**音樂比語音低 19.8 dB**；分曲子看是 20.1／26.1／17.9 dB（第一版同樣量法約是 14／20／12 dB）。音效與語音重疊的地方，最接近的也比語音低 9.5 dB，沒有蓋過人聲的，音效音量沒改。語音沒有做任何正規化。
- 澄清一件事：主 session 量到「音樂比人聲大」，用的是第一版的 `bgm.wav`，那個檔當時是還沒降 12 dB 的原始音量，成品裡的音樂其實比它小 12 dB。為免再誤會，現在 `bgm.wav`、`sfx.wav` 就是成品裡實際的音量，每次出片另寫一份 `render/loudness.json`。不過第三首曲子在第一版確實只比語音低約 12 dB，句尾輕收的字被蓋住是可能的，所以退後功能還是加了。
- **配音更新**：語音清單在 00:07 更新（36 個逐句檔換新：旁白與結尾幾句），時間表重排，**新片長 12 分 36 秒**（原 12 分 26 秒）。結尾「那么……」在清單裡是 1.23 秒（主 session 說來源約 2.3 秒；切成逐句檔時頭尾的靜音被去掉了，是否切太多請配音那邊確認）。
- 用時 1496 秒。測試增為 28 個（全套 63 個全過）。

### 留給整合階段（S6）的問題
1. **間隔在有畫面之後是否仍合適**：現在的規則是腳本的等待算進間隔。若覺得轉場後開口太快或太慢，調 `render.gaps`。
2. 配音換新檔之後只要重跑 `python -m pipeline render --scene act33side_st01` 即可（約 26 分鐘）；只換了音檔而每句長度沒變時，畫面不必重畫，但目前沒有「只重混音軌再接回舊畫面」的捷徑指令，要的話可以加。
3. 還沒做的指令：`musicvolume`（BB-ST-1 沒用到；遇到會在時間表的警告裡列出）、選項 `[Decision]`、`Effect`／`bgeffect`／`curtain`／`interlude` 等其他場次才有的演出。對白裡的 `<color>`、`<i>` 標籤目前直接去掉（全巴別塔共 36 處）。
4. 背景圖原檔只有 1024×576，放大到 1920×1080 會略糊，這是素材來源的解析度。
5. Mon3tr 的叫聲：腳本本來就在那幾句播放遊戲音效（`char_Mon3tr`、`Mon3tr_n`），已經在音效軌裡，不必另外配。
6. 片頭字卡的最終文字待定（見上）。

## 補充 2026-10-05（開工前必讀；與上文衝突時以這裡為準）
- 在 worktree `.claude/worktrees/renderer` 工作。worktree 裡的 `out`、`data`、`assets`、`.venv` 是連到主倉庫的捷徑。
- **語音不再是 `audio/<line_id>.wav`。** 讀 `out/<scene>/voice_manifest.json`（格式與節奏規則見 `docs/01-architecture.md`「追加 2026-10-05」）。這份清單由另一個 session（`voice-lines`）同時在做；它還沒出來之前，用 `out/act33side_st01/lines.json` 的 158 行自己生一份佔位清單（每句用 `say` 或靜音，長度按字數），格式必須相同，之後直接換檔就能用。
- **字卡是有聲的**，而且字卡的 line_id 是另一套（`<scene>_s###`，`pipeline/stickers.py`）。字卡停留時間要蓋住語音。
- 不配音的行（「……」、叫聲描述、未知語言）畫面照常顯示文字。選項（`[Decision]`）暫不處理。`Dr.{@nickname}` 畫面上照原文顯示（暱稱用「博士」）。
- 通則：畫面與文字一律照原版，不刻意與遊戲產生差異。
- 間隔數值（同一人 0.8 秒、換人 0.6 秒、不配音 1.0 秒）做成設定檔可調；`gap_before` 優先。
- 素材由另一個 session（`assets`）同時在下載，清單是 `out/<scene>/assets_manifest.json`。它還沒出來之前，缺的素材用色塊與文字佔位，不要自己去抓素材。
- BGM 與音效軌照原設計做，但第一支影片可以先只有語音軌能出片；三軌分開成檔這點不變。
- 片頭「本片語音為 AI 生成」字卡（`--intro-card`）在這裡做掉。
