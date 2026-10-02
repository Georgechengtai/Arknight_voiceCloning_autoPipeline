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
