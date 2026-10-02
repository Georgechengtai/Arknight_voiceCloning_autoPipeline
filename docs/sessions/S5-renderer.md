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
（session 結束時填寫）
