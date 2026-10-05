# 01 管線架構與資料契約

## 總覽

```
[Kengxxiao gamedata]      [PRTS 索引/素材]        [arknights-audio voice_cn]   [ElevenLabs Voice Design]
        │                        │                          │                          │
        ▼                        ▼                          ▼                          ▼
 (1) parse ──► timeline.json ──► (2) assets ──► assets/    (3) casting ──► casting.yaml + refs/<speaker>/*.wav + voices.json
        │                                                     │
        └──────────────► tts_manifest.json ◄──────────────────┘
                                 │  rsync → SCRP
                                 ▼
                        (4) tts_batch (3090)  ──► out/<scene>/audio/<line_id>.wav + qc_report.json
                                 │  rsync ← SCRP        (ElevenLabs 句子在 Mac 直接呼叫 API，不上叢集)
                                 ▼
                        (5) render (Mac) : timeline + audio durations ──► frames (Playwright) ──► ffmpeg ──► out/<scene>/<scene>.mp4
                                 │
                                 ▼
                        (6) review : qc_report、人工聽審清單、投稿檢查表
```

階段 (1)(2)(3)(5)(6) 在 Mac；(4) 在 SCRP。每階段是獨立 CLI 子命令，輸入輸出都是檔案，可單獨重跑。

## 目錄規範

```
Arknight_voiceCloning_autoPipeline/
├── pipeline/                 # Python 套件（CLI：python -m pipeline <cmd>）
│   ├── parse.py              # (1) 腳本 → timeline.json
│   ├── assets.py             # (2) 素材解析與下載
│   ├── casting.py            # (3) 說話者統計、選角表骨架、參考音挑選
│   ├── tts/                  # (4) manifest 生成、引擎介面（indextts2 / elevenlabs）、ASR 質檢
│   ├── render/               # (5) Playwright 驅動、ffmpeg 合成
│   │   └── web/              #     HTML/Canvas 渲染器（純前端，無框架或極輕量）
│   └── common/               # 設定、日誌、路徑
├── cluster/                  # SCRP 端：環境建置腳本、sbatch 模板、tts_batch.py（自包含）
├── config/
│   ├── settings.yaml         # 解析度、fps、停留規則、閾值
│   ├── casting.yaml          # 選角表（入庫）
│   └── lexicon.yaml          # 專有名詞拼音表（入庫）
├── data/gamedata/            # 下載的腳本與 excel 表（不入庫）
├── assets/{bg,char,image,audio}/   # PRTS 下載素材（不入庫）
├── refs/<speaker>/           # 參考音（不入庫）
├── cache/prts/               # 索引快取（不入庫）
├── out/<scene_id>/           # timeline.json、tts_manifest.json、audio/、frames/、*.mp4、qc_report.json（不入庫）
└── docs/
```

場景 id 規範：`act33side_st01`（取 storyTxt 最後一段去掉 `level_` 前綴）。

## 資料契約

### timeline.json（(1) 輸出，(2)(3)(5) 輸入）

```json
{
  "scene_id": "act33side_st01",
  "story_code": "BB-ST-1", "story_name": "未完成的告别", "avg_tag": "幕间",
  "source": "activities/act33side/level_act33side_st01",
  "coord_system": {"w": 1280, "h": 720},
  "events": [
    {"i": 0,  "cmd": "background", "args": {"image": "bg_laccolith", "screenadapt": "coverall"}},
    {"i": 1,  "cmd": "blocker",    "args": {"a": 0, "fadetime": 1, "block": true}},
    {"i": 2,  "cmd": "charslot",   "args": {"slot": "m", "name": "avg_npc_053", "group": "avg_npc_053", "face": null, "body": null, "duration": 1}},
    {"i": 3,  "cmd": "line", "line_id": "act33side_st01_0001", "kind": "dialogue",
              "speaker": "负伤的雇佣兵", "sprites_on_stage": ["avg_npc_053"], "text": "把脖子上的牌子给我死死护好！……",
              "tts_text": null, "emotion": null},
    {"i": 4,  "cmd": "line", "line_id": "act33side_st01_0002", "kind": "narration", "speaker": null, "text": "卡兹戴尔地区，疤痕商场"},
    {"i": 5,  "cmd": "sticker", "args": {"id": "st1", "text": "六十四年前", "x": 300, "y": 325, "size": 24, "width": 700, "alignment": "center", "delay": 0.04, "duration": 1}},
    {"i": 6,  "cmd": "playmusic", "args": {"intro": "drift_intro", "key": "drift_loop", "volume": 0.6}},
    {"i": 7,  "cmd": "playsound", "args": {"key": "d_avg_snowstormlp", "loop": true, "channel": "bgs1", "volume": 0}}
  ]
}
```

規則：
- 指令名一律小寫；數值轉 number、`true/false` 轉 bool；`$` 前綴從音訊鍵去掉。
- 每個 `line` 事件有唯一 `line_id` = `<scene_id>_<4 位序號>`，`kind` ∈ dialogue / narration / subtitle。Sticker 不是 line（不配音）。
- `tts_text`：送 TTS 的文本（去星號舞台提示、全角標點正規化、套用 lexicon 的替換），由 (3) 填寫；為 null 時用 `text`。
- `sprites_on_stage`：解析器維護的當前台上立繪組（供選角以「說話者＋立繪」判身份）。
- 時長不在 timeline 裡：(5) 讀 audio/ 的實際 WAV 長度決定每句停留。

### casting.yaml（(3) 產生骨架，人工填寫，入庫）

```yaml
defaults:
  pause_after_line_s: 0.5
  engine_for_operators: indextts2
  engine_for_designed: elevenlabs
speakers:
  特蕾西娅:  {role: operator, char_id: char_XXXX_theresa, engine: indextts2, refs: refs/特蕾西娅/}
  凯尔希:    {role: operator, char_id: char_003_kalts,     engine: indextts2, refs: refs/凯尔希/}
  旁白:      {role: narrator, engine: elevenlabs, voice_id: "<eleven voice id>", design_prompt: "..."}
  博士:      {role: doctor,   engine: elevenlabs, voice_id: "...", design_prompt: "巴别塔时期的博士……"}
  特雷西斯:  {role: npc_major, engine: elevenlabs, voice_id: "..."}
  负伤的雇佣兵: {role: npc_minor, pool: male_rough}
pools:
  male_rough:   {engine: elevenlabs, voice_id: "..."}
  female_young: {engine: elevenlabs, voice_id: "..."}
identity_overrides:          # 同名不同人 / 假名 → 真身，鍵為 "speaker|sprite_group"
  "？？？|avg_4132_ascln_1": 阿斯卡纶
  "“阿米娅”|avg_npc_1360_1": 阿米娅
unassigned_default: {pool: male_neutral}
```

硬性約束：`engine: elevenlabs` 的條目**不得**有 `refs`；管線在載入時檢查並拒絕（D3 合規）。

### tts_manifest.json（(3) 輸出，(4) 輸入）

```json
{"scene_id": "act33side_st01", "sample_rate": 24000,
 "items": [
  {"line_id": "act33side_st01_0001", "speaker": "负伤的雇佣兵", "engine": "elevenlabs", "voice_id": "...", "text": "把脖子上的牌子给我死死护好！", "emotion": null},
  {"line_id": "act33side_st01_0003", "speaker": "凯尔希", "engine": "indextts2", "refs": ["refs/凯尔希/CN_011.wav", "refs/凯尔希/CN_017.wav"], "text": "……", "emotion": null, "seed": 0}
 ]}
```

(4) 只處理 `engine == indextts2` 的項目；elevenlabs 項目由 Mac 端 `pipeline tts --engine elevenlabs` 處理。兩邊都寫到同一個 `out/<scene>/audio/<line_id>.wav`，24 kHz 單聲道。

### qc_report.json（(4) 輸出）

```json
{"items": [{"line_id": "...", "attempts": 2, "cer": 0.03, "asr_text": "...", "status": "ok|retry_ok|flag", "duration_s": 3.2}],
 "summary": {"total": 127, "ok": 120, "flag": 7}}
```

CER（字錯率）閾值預設 0.10；`flag` 項目列入人工聽審。

## 節奏規則（(5) 實作，settings.yaml 可調）

- line 有音訊：顯示該句 → 播放音訊 → 音訊結束後再停 `pause_after_line_s`（0.5 s）→ 下一事件。
- line 無音訊（例如 flag 後人工決定靜音）：停留 1.0 s + 0.12 s × 字數。
- `delay(time)`：照腳本。`blocker` fade：照 fadetime（預設 0.25）。`sticker`：出現後至被移除事件為止；若腳本沒有移除則跟隨下一個 line 結束。
- `playmusic`：intro 播完接 loop 無縫循環至 `stopmusic` 或下一 `playmusic`；`musicvolume`/`soundvolume` 的 fadetime 作線性漸變。
- 多個 `charslot` 連續出現視為同一幀內的狀態變更，不額外耗時（除非帶 duration，則作滑入/淡入動畫）。

## 渲染器（(5)）約定

- 純 HTML + Canvas 2D（或 DOM + CSS），無打包工具也能 `file://` 開啟；`window.renderer.seek(t_ms)` 必須是**確定性**的：給定時間回傳同一畫面，不用 requestAnimationFrame 真實時鐘。
- Playwright（Python）以 1/30 s 步進呼叫 `seek`，截 PNG 到 `out/<scene>/frames/`（或直接 pipe 到 ffmpeg stdin 省磁碟）。
- 音軌在 Python 端用 ffmpeg filter_complex 混：語音軌（按時間軸 adelay）、BGM 軌、音效軌，三軌獨立成檔後再混，BGM 軌可關（D11 風險對策）。
- 文字：思源黑體 / Noto Sans CJK SC；對白框樣式近似遊戲即可，不必像素級還原。

## 叢集端（(4)）約定

- `cluster/tts_batch.py` 自包含：讀 manifest，對每項載入 refs、合成、寫 WAV、ASR 回檢、重試、寫 qc_report。不 import 專案其他模組。
- `cluster/setup_env.sh`：建 conda 環境（放 `~/large-data/conda`），裝 IndexTTS-2 與 FunASR，下載權重到 `~/large-data/models/`。
- `cluster/job.sbatch`：`--gpus=rtx3090 -c 8 --mem=40G -t 0-12`，以 `MANIFEST` 環境變數指向輸入。
- Mac 端 `pipeline cluster push/pull` 封裝 rsync（只傳 manifest、refs、audio、report）。

## 追加 2026-10-04（S1 實作後的 timeline 契約補充）

機器可讀的完整定義在 `pipeline/schemas/timeline.schema.json`，解析器寫檔前一律驗證。上面的範例仍然成立，實作多了這些：

- 每個 line（對白、旁白、字幕都一樣）固定帶 `sprites_on_stage`、`focus_group`、`tts_text`、`emotion`。
  - `sprites_on_stage`：charslot 的立繪依 l、m、r 排序，其後是 charactercutin 的立繪。
  - `focus_group`：被打亮的那個立繪組（多半就是說話者）；無法確定時為 null。
- line 的選用欄位：`rich_text`（原文帶 `<color>` 標籤或 `{@nickname}` 時才有；`text` 永遠是清理後的純文字）、`multiline: {block, end}`（`[multiline]` 區塊的一段；不合併，同 `block` 的各段在同一個對話框接續顯示）、`args`（字幕的座標字號等）。
- 頂層多了 `header`（腳本首行 `[HEADER]` 的參數）與 `stats`（事件數、各類句數、規劃口徑句數）。
- 一般指令事件是 `{i, cmd, args}`；`args` 的鍵一律小寫。charslot 與 charactercutin 帶 name 時多出 `group`、`face`、`body`。未知指令多一個 `raw`；解析失敗的行是 `cmd: "_unparsed"`，帶 `raw`、`error`、`src_line`。
- 帶文字的 `[Subtitle]` 是 `kind: subtitle` 的 line；無參數的 `[subtitle]` 是清除字幕的指令事件。`[Decision]` 目前是指令事件，不是 line。
- 遊戲資料的實際位置：`data/gamedata/excel/<表>.json`、`data/gamedata/story/<storyTxt>.txt`。

## 追加 2026-10-05（BB-ST-1 配音完成後：語音軌的契約與節奏規則的修訂）

BB-ST-1 的 143 句配音已完成並經專案擁有者聽過六版（過程與結論見 `docs/00-decisions.md` 當日各節）。實作與上面的原設計有幾處不同，以這一節為準。

### 語音的交付格式：`out/<scene>/voice_manifest.json` ＋ `out/<scene>/voice/<line_id>.wav`

原設計的 `tts_manifest.json`／`audio/<line_id>.wav`／`cluster/tts_batch.py` 沒有照做。實際做法是「導演表 → 兩種引擎各自合成 → 切成逐句檔」，渲染器只認下面這份清單：

```json
{"scene": "act33side_st01", "sample_rate": 44100,
 "lines": [
  {"line_id": "act33side_st01_0001", "speaker": "旁白", "engine": "elevenlabs", "path": "voice/act33side_st01_0001.wav", "dur": 4.52, "gap_before": null},
  {"line_id": "act33side_st01_s002", "speaker": "梦中的巨人", "engine": "elevenlabs", "path": "voice/act33side_st01_s002.wav", "dur": 3.10, "gap_before": null},
  {"line_id": "act33side_st01_0020", "speaker": "阿斯卡纶", "engine": null, "path": null, "dur": 0, "gap_before": null}
 ]}
```

- 每個「要顯示文字的行」一筆，順序＝播放順序：timeline 的 line，加上帶文字的字卡（編號 `<scene>_s###`，見 `pipeline/stickers.py`）。清單由 `tools/scene_lines.py` 的結果加上音檔資訊組成。
- 不配音的行（「……」、叫聲描述、未知語言、只有標點的字卡）`path` 為 null、`dur` 為 0，畫面照常顯示。
- 音檔：單聲道 44.1 kHz WAV，已去頭去尾、句尾留 0.08 秒並淡出 0.06 秒、音量已統一（有聲部分約 -20 dB）。渲染端不要再做音量正規化。
- `gap_before`：導演表指定「這句開口前要留幾秒」（換場、需要留白的告別等）；null 表示用預設。

### 節奏規則（取代上面「line 有音訊」那一條）

- 一句的顯示區間＝開口前的間隔＋音檔長度。開口前的間隔：`gap_before` 有值就用它；否則**同一人接著說 0.8 秒、換人說話 0.6 秒**（專案擁有者的結論：兩句帶感情的話緊貼著聽起來就是棒讀）。全場第一句為 0。
- 不配音的行：停留 1.0 秒（原設計按字數算，試聽時用的是固定 1.0 秒）。
- 字卡現在是有聲的：字卡的文字照腳本的位置與時機顯示，停留時間至少要蓋住它的語音。同一張字卡若腳本的顯示時間比語音短，以語音為準往後順延。
- 以上間隔是整場試聽（純音軌）時定的。加上畫面、BGM 之後是否仍合適，由整合階段的全片審看決定，數值請做成可調設定。

### 目前還沒有、需要補的東西

- ElevenLabs 的音檔是「同一人連續幾句合成一段」（BB-ST-1 共 38 段涵蓋 109 句），只有段的時間、沒有逐句的時間。要用語音辨識的逐字時間對回原文切開（`cluster/scene_variants.py` 裡有現成的對齊與切點函式）。
- 沒有背景音樂、音效、Mon3tr 的叫聲。

## 追加 2026-10-05（S5 渲染器實作後：時間表的契約與節奏的落地方式）

渲染階段已實作在 `pipeline/render/`，上面「節奏規則」「渲染器約定」兩節與本節不同之處以本節為準。

### 指令

```
python -m pipeline render --scene act33side_st01            # 出 out/<scene>/<scene>.mp4 與 <scene>_nobgm.mp4
python -m pipeline render --scene … --intro-card            # 片頭加「本片语音为 AI 生成」字卡（文字與秒數在設定檔）
python -m pipeline render --scene … --schedule-only         # 只算時間表；--audio-only 再加音軌，不畫畫面
python -m pipeline render --scene … --voice-manifest <路徑> --tag <標記>   # 換一份語音清單，輸出改放 out/<scene>/render-<標記>/
python -m pipeline render-placeholder --scene …             # 語音清單還沒出來時：用 lines.json 生佔位清單到 out/<scene>/placeholder/
python -m pipeline render-preview --scene …                 # 本機預覽頁（拖曳條＋播放），不用等出片就能看畫面
```

工作檔都在 `out/<scene>/render/`：`schedule.json`、`voice.wav`、`bgm.wav`、`sfx.wav`、`mix.wav`、`mix_nobgm.wav`、`video.mp4`（無聲畫面）。同名的舊影片不會被覆蓋，會先改名（加上日期時間）留著；要直接蓋掉加 `--force`。

三個輸入：`timeline.json`、`voice_manifest.json`（路徑相對於清單所在的目錄）、`assets_manifest.json`（沒有這個檔、或裡面缺某個素材時，畫面用色塊加文字佔位、聲音靜音，並在時間表的 `warnings` 列出）。

### schedule.json（時間表）

`pipeline/render/schedule.py` 的 `build_schedule()` 是純函式；渲染器與混音都只讀它的結果，不自己算節奏。時間單位是秒，取到毫秒。

```json
{"scene_id": "…", "fps": 30, "width": 1920, "height": 1080, "coord": {"w": 1280, "h": 720},
 "duration": 746.484, "frames": 22395,
 "intro": null,
 "events": [{"i": 0, "cmd": "blocker", "t": 0.0}],
 "lines":  [{"line_id": "…_0001", "kind": "narration", "speaker": "旁白", "voiced": true, "gap": 0.0,
             "t": 4.0, "t_voice_end": 12.0, "t_end": 12.91, "audio": "out/…/voice/…_0001.wav"}],
 "layers": {"backgrounds": [], "images": [], "sprites": [], "blockers": [], "shakes": [],
            "stickers": [], "subtitles": [], "dialogs": []},
 "audio":  {"voice": [], "music": [], "sounds": []},
 "approx": ["backgroundtween", "camerashake", "imagetween"], "warnings": []}
```

- `events`：每個 timeline 事件的開始時刻（除錯與測試用）。`lines`：每個要顯示文字的行（含字卡），`t` 是字出現、也是開口的時刻，`t_voice_end` 是說完，`t_end` 是畫面往下走的時刻。
- `layers` 是畫面的全部內容，每一項都帶起訖時間：背景與插圖（含縮放平移的補間）、立繪（位置、大小、淡入淡出、移動、震動、每段時間是亮是暗）、黑幕色塊、鏡頭震動、字卡、字幕、對話框。
- `approx` 列出只做了近似的指令（鏡頭震動用正弦位移；背景／插圖的補間用等速）。

### 節奏：間隔放在哪裡

「開口前的間隔」（`gap_before`，或同一人 0.8 秒、換人 0.6 秒）在畫面上是**上一句的字多留一會兒**，下一句的字與聲音同時出現（任務書的驗收要求字與聲音的起點差小於 0.1 秒；若把間隔放在下一句的字出現之後，字會比聲音早 0.6–0.8 秒）。

腳本自己的等待（`Delay`、會等待的黑幕淡入淡出）**算進間隔，不重複加**：兩句之間腳本已經等了 3 秒，就不再另外加 0.6 秒；腳本只等了 0.2 秒，就補到 0.6 秒。理由：這些間隔是在純音軌時定的，其中換場的 2 秒本來就是在模擬轉場，現在有真的轉場了。緊接轉場的句子，字至少再留 0.3 秒才消失。整場因此是 12 分 26 秒（純音軌 10 分 54 秒，多出的是腳本的轉場與停頓）。

不配音的行照舊停 1.0 秒，這 1.0 秒對下一句來說也算已經等過的時間（與純音軌的算法一致）。

以上數值都在 `config/settings.yaml` 的 `render.gaps`；`absorb_script_time: false` 可改回「間隔與腳本等待相加」。語音清單裡的 `gap_rules` 目前只當說明，實際數值以設定檔為準。

### 畫面的決定（與任務書原文不同之處）

- **圖層順序**：背景 → 插圖（`Image`）→ 立繪 → 黑幕色塊 → 字卡與字幕 → 對話框。任務書原文把字卡放在黑幕之下，但腳本的用法是「先把畫面壓暗六成，再出字卡」，字卡若在黑幕下會跟著變暗，所以放在上面。
- **立繪位置**：素材清單的 `pos`、`size` 是「圖片畫成 size×size（遊戲座標），中心在該位置的 x ＋ pos.x、離畫面底邊 pos.y 高」；三個位置的中心 x 是 440／640／840。兩者都已對照 PRTS 播放器的原始碼（`Widget:ScenarioSimulator` 的 `charPos`：960 寬畫布上的 330／480／630）。第一版影片出片時 PRTS 連不上，左右位置用的是猜的 320／960（太靠兩邊），當晚連上後已修正並重出。立繪站得近會互相遮到，所以壓暗的先畫、亮的（正在說話的）畫在上面。
- **說話者以外的立繪亮度** 0.6（任務書寫 85%；遊戲裡壓暗得比較明顯）。可在 `render.stage.dim_brightness` 調。
- **打亮規則**（同 PRTS 播放器）：`focus` 指定位置 → 只有該位置亮；`focus="n"` → 全暗；`all` 或清空之後 → 全亮；換上新立繪而沒寫 `focus` → 亮的是那個位置。只寫 `posto` 的移動是「從目前位置再移這麼多」。
- **字型**：依序找 Noto Sans CJK SC、思源黑體、蘋方。這台 Mac 已用 Homebrew 裝了 Noto Sans CJK SC（`brew install --cask font-noto-sans-cjk-sc`），現在用的是它。
- 靜止的畫面不重複截圖：渲染器先把「這一刻畫面上有什麼」算成一份資料，與上一幀相同就沿用上一張圖。`seek` 仍是確定性的。

### 音軌

- 語音：照時間表把每句放到開口的時刻，不調音量。
- 音樂：前奏播一次，接循環段重複到 `stopmusic` 淡出；音量是腳本的 `volume` 再降 `render.audio.bgm_gain_db`（−12 dB）。**有人說話時音樂自動再退 6 dB**（`render.audio.duck`：開口前 0.25 秒開始退、說完 0.6 秒內回來、兩句相隔不到 1.5 秒就不回升；依時間表的語音時段計算，不是聽音量即時壓，所以每次結果相同）。
- 音效：一次性的照原長播放；循環的（風雪聲）照 `soundvolume`／`stopsound` 的音量折線。再降 `sfx_gain_db`（−6 dB）。
- 三軌各自成檔，最後只相加，混成有音樂與無音樂兩版。**`bgm.wav`、`sfx.wav` 已經包含上述增益與退後，就是成品裡實際的音量**（第一版的 `bgm.wav` 是還沒降 12 dB 的原始音量，直接拿它和語音比會以為音樂比人聲大）。每次出片會把「有人說話時」三軌的響度寫到 `render/loudness.json`。
- BB-ST-1 實測（只量有人說話的時段）：音樂比語音低 20.0／26.1／17.7 dB（三首曲子原始音量不同，沒有另外拉齊）；與語音重疊的音效最接近的也低 9.5 dB。
- 循環段是 MP3，接縫處可能有極短的空隙。
