# 02 外部資料來源（全部於 2026-10-02 實測核實）

> 核實環境只放行 github.com、raw.githubusercontent.com、prts.wiki（主域）。
> media.prts.wiki 與 torappu.prts.wiki 在核實環境被擋，其 URL 格式從 PRTS 播放器原始碼推得，**S2 必須在 Mac 上實測**。

## 1. 劇情腳本：Kengxxiao/ArknightsGameData

- 原始 txt：`https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/story/<storyTxt>.txt`
  例：`activities/act33side/level_act33side_st01`
- 場景索引：`zh_CN/gamedata/excel/story_review_table.json`
  - 巴別塔鍵 `act33side`，`name` = 巴别塔，`infoUnlockDatas[]` 23 項，每項有 `storyCode`（BB-ST-1 / BB-1 …）、`storyName`、`avgTag`（幕间 / 行动前 / 行动后）、`storyTxt`。
- 幹員語音表：`zh_CN/gamedata/excel/charword_table.json`（11 MB）
  - `charWords[<charId>_<lang>_<voiceId>]`：`charId`、`voiceId`（如 CN_001）、`voiceText`（該語音的台詞原文，可用於挑參考音與 ASR 核對）、`voiceTitle`。
  - `voiceLangDict[<charId>].dict` 的鍵為語言：CN_MANDARIN、JP、EN、KR、CN_TOPOLECT、LINKAGE 等。統計：455 人有語音，CN_MANDARIN 431、JP 431、EN 406、KR 406、僅 LINKAGE 24。
- 角色名→charId：`zh_CN/gamedata/excel/character_table.json`（`name` 欄）。注意同名多版本（如 阿米娅 char_002_amiya / char_1001_amiya2 / char_1037_amiya3）：選角時明確指定。
- 建議取法：不要整庫 clone（數 GB）。用 raw URL 逐檔下載，或 `git clone --filter=blob:none --sparse` 後 `git sparse-checkout set zh_CN/gamedata/excel zh_CN/gamedata/story/activities/act33side`。

### 腳本語法（實測巴別塔）

- 指令行：`[Cmd(key=value, key="value")]`，指令名大小寫不一致（`Delay`/`delay`、`PlaySound`/`playsound`、`Background`/`background`、`Dialog`/`dialog`），**解析時一律小寫化**。
- 對白：`[name="说话者"]台词文本`。可帶其他屬性（如 `[name="X", ...]`）。
- 旁白：不以 `[` 開頭的純文字行。
- `[dialog]`／`[Dialog]`：清空對話框（常跟在一段對白後）。
- `[charslot(slot="m", name="avg_npc_1305_1#8$1", duration=1)]`：立繪。`slot` 取 l / m / r；`name` 格式 `<group>#<face>$<body>`，face/body 可省略；`[charslot]` 無參數＝清空所有立繪。另有 `[character(name=..., name2=..., focus=...)]` 舊語法（巴別塔未見，其他章節有，解析器要支持）。
- `[Background(image="49_g8_scarmarketcamp", screenadapt="coverall")]`、`[Image(image="avg_5_7_shining", fadetime=0, screenadapt="coverall")]`（Image 是全屏 CG/插圖，蓋在背景上）。
- `[Blocker(a=1, r=0, g=0, b=0, fadetime=0, block=true)]`：全屏色塊，a 透明度；用於黑幕/淡入淡出。
- `[Sticker(id="st1", text="六十四年前", duration=1, x=300, y=325, alignment="center", size=24, delay=0.04, width=700)]`：浮動字卡，座標為 1280×720 遊戲座標；再出現同 id 無 text 的 `[Sticker(id="st1", duration=1)]` 表示移除。
- `[Subtitle(text=..., ...)]`：底部字幕式文字（旁白變體），`[subtitle]` 清除。
- `[PlayMusic(intro="$drift_intro", key="$drift_loop", volume=0.6)]`、`[stopmusic]`、`[musicvolume(...)]`。
- `[playsound(key="$d_avg_snowstormlp", loop=true, channel="bgs1", volume=0)]`、`[SoundVolume(volume=0.5, channel="bgs1", fadetime=2)]`、`[StopSound(channel=...)]`。
- `[Delay(time=1.5)]`、`[CameraShake(duration=0.3, xstrength=30, ystrength=30, vibrato=30, randomness=90, fadeout=true, block=false)]`、`[interlude(...)]`（過場遮罩）、`[curtain]`、`[bgeffect]`、`[Effect]`、`[ImageTween]`、`[HEADER(...)]`（首行，忽略）、`[multiline]`（多行對白連續顯示）。
- 文本中 `*萨卡兹粗口*` 這類星號包圍是舞台提示，TTS 前要處理（建議：念出內容但去掉星號，或按表替換）。

## 2. 幹員原聲：PseudoMon/arknights-audio

- `https://github.com/PseudoMon/arknights-audio`，MP3，資料夾 `voice`（日語）、`voice_cn`、`voice_kr`、`voice_en`、`music`、`battle`、`enemy`。
- `voice_cn/<charId>/<voiceId>.mp3`（如 `voice_cn/char_002_amiya/CN_001.mp3`），檔名與 charword_table 的 voiceId 對應（S3 實測確認）。
- 倉庫極大（部分 clone 即 > 7 GB，`--filter=blob:none` 在代理後未生效）。**不要整庫 clone**；用 raw URL 只下載選角表需要的角色（每角色 10–30 個檔）。
- 維護者說明「僅供教育用途」，可索取無損 WAV。

## 3. PRTS wiki（視覺素材、音訊索引、播放器參考）

### 索引頁（raw wikitext，MediaWiki）
`https://prts.wiki/index.php?title=<頁名>&action=raw`

| 頁 | 大小 | 格式 | 用途 |
|---|---|---|---|
| `Widget:Data_Image` | 192 KB | 每行 `key,url` | 背景與插圖。**背景鍵 = `bg_` + 腳本 image 名**（`bg_bg_laccolith`、`bg_49_g8_scarmarketcamp`）；Image() 插圖鍵 = 原名（`avg_5_7_shining`）。 |
| `Widget:Data_Char` | 985 KB，12 952 行 | 每行 `key,url` | 立繪單檔。鍵形式有三種：`<group>-<face>$<body>`（`avg_4132_ascln_1-4$1`）、`<group>$<body>`（`avg_npc_1306_1$1`）、`<group>`（`avg_npc_053`）、舊式 `<group>_1`（`npc_10002_1`）。 |
| `Widget:Data_Link` | 697 KB | JSON `{group: {pos:{x,y}, size:{x,y}, array:[{alias,name}]}}` | 每個立繪組的錨點座標、尺寸與全部變體清單。**解析順序：先用 Data_Link 找組，再在 array 中按 face/body 選變體，最後到 Data_Char 取 URL。** |
| `Widget:Data_Audio` | 178 KB | JSON `{key: "Sound_Beta_2/..."}` | 音訊鍵→相對路徑。例 `drift_intro → Sound_Beta_2/Music/act9d0d0/m_avg_drift_intro`。 |
| `Widget:Data_Override` | 28 KB | 文字 | 標題覆寫等，暫不需要。 |
| `模板:剧情模拟器`、`Widget:ScenarioSimulator`（164 KB，舊版播放器全部 JS/CSS）、`Widget:StoryPlayer`（新版，PixiJS，bundle 在 `https://static.prts.wiki/widgets/production/StoryPlayer.*.js`） | | | 渲染規則參考（見下）。 |

### 從 ScenarioSimulator 原始碼推得的規則
- 音訊 URL：`"https://torappu.prts.wiki/assets/" + path.replace("sound_beta_2","audio") + ".mp3"`（原碼對小寫 `sound_beta_2` 做替換，故路徑先小寫化；大小寫是否敏感 S2 實測）。
- 以 `$` 開頭的鍵查 Data_Audio；以 `@` 開頭的為直接路徑。
- 播放器基準畫布 960×540，`pos_multiply = 0.75`，即遊戲腳本座標系為 **1280×720**；Sticker 的 x/y/width、size 乘 0.75 得畫布像素。本專案輸出 1920×1080 → 乘 1.5。
- 立繪變換用 CSS matrix，`offsetx` 預設 480（畫布中心），`offsety` 向上為正。Data_Link 的 `pos`/`size` 為 1280×720 系下的錨點與圖尺寸；精確語義（錨點是底中還是左上）S5 要對照 ScenarioSimulator 的 `case "l"/"m"/"r"` 分支確認。
- Blocker 預設 fadetime 0.25 s。
- 對白文字預設字號 18 px（畫布 960 系）。

### 巴別塔覆蓋率（已核實）
- 背景 48/48；Image 插圖全部命中；charslot 立繪名 199/199 可解析；BB-ST-1 音訊鍵 18/18。

### 行為規範
- PRTS 對連續請求會 `Connection reset by peer`：每請求間隔 ≥ 1 s，失敗退避重試 3 次，結果快取到 `cache/prts/`。
- 一次只下載當前場景清單需要的素材，不要全量鏡像。
- 不抓 HTML 頁面；只用 `action=raw` 與 `api.php`。

## 4. 已排除的來源（避免重複踩坑）
- `Aceship/Arknight-Images`：`avg/backgrounds`、`avg/characters` 僅有舊素材，巴別塔背景與 `avg_npc_13xx` 立繪全部 404。
- `yuanyan3060/ArknightsGameResource`：無 avg 劇情素材。
- `050644zf/ArknightsStoryTextReader`：純文字閱讀器（Vue），無渲染器；其解析腳本在 `050644zf/ASTR-Script`，可作解析器參考（MIT）。
