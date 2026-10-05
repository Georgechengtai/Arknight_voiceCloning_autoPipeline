# S1 專案骨架、腳本解析器、timeline.json

## 目標
建立 `pipeline/` Python 套件與 CLI；實作 `python -m pipeline parse --scene act33side_st01` 產出符合 `docs/01-architecture.md` 契約的 `out/act33side_st01/timeline.json`；對巴別塔全部 23 場解析無錯。

## 步驤
1. 骨架：Python 3.11、`pyproject.toml`（建議 uv 或 pip）、`pipeline/__main__.py` 以 argparse/typer 提供子命令 `fetch-gamedata`、`parse`、`speakers`。`config/settings.yaml` 初版（1920×1080、30 fps、pause 0.5、CER 0.10）。
2. `fetch-gamedata`：下載 `story_review_table.json`、`charword_table.json`、`character_table.json` 與指定活動（預設 act33side）全部 story txt 到 `data/gamedata/`（raw.githubusercontent URL，見 `docs/02-data-sources.md` §1），有快取就跳過。
3. `parse`：
   - 指令行 tokenizer：`[cmd(k=v, k="v", ...)]`、`[cmd]`、`[name="X"]text`、純文字旁白。注意參數值可含逗號與引號內空格（Sticker text、`size="1280, 100"`）；用狀態機而非 split。
   - 指令名小寫化；數值/布林轉型；音訊鍵去 `$`。
   - charslot name 拆成 group / face / body（`avg_npc_1305_1#8$1` → group `avg_npc_1305_1`, face 8, body 1；`npc_10002` → group `npc_10002`）。同時支持舊語法 `[character(name=, name2=, focus=)]`。
   - 維護 `sprites_on_stage`；`[charslot]`/`[character]` 無參數＝清空。
   - 產生 `line` 事件與 `line_id`。`[Subtitle(text=...)]` 作 `kind: subtitle` 的 line（配音用旁白聲線）；`[multiline]` 區塊內的連續對白合併為一個 line 或保持多 line——選一種並記錄。
   - 未知指令照原樣保留 `{"cmd": name, "args": {...}, "raw": "..."}`，不報錯。
4. `speakers`：輸出 `out/<scene or act>/speakers.csv`：speaker、sprite_group（出現時台上的立繪，可多個）、line_count、sample_lines(3)。供 S3 選角。
5. 測試：pytest，至少覆蓋 tokenizer 邊界、charslot 拆分、BB-ST-1 行數 = 127（本規劃統計口徑：`[name=...]` 行＋非 `[` 開頭非空行；若你的口徑不同，記錄差異原因）。

## 驗收
- 23 場全部解析，無例外；統計與 `docs/00-decisions.md` 的數字在 ±2% 內（差異寫明原因）。
- `timeline.json` 通過一份 JSON Schema（請一併寫 `pipeline/schemas/timeline.schema.json`）。
- `speakers.csv` 對巴別塔列出 104 ± 3 個說話者。

## 邊界
- 不下載素材、不呼叫任何 TTS。
- 不解析 ja_JP / en_US 腳本（D2）。

## 完成記錄
2026-10-04，分支 `s1-parser`。

### 做了什麼
- 骨架：`pyproject.toml`（Python ≥ 3.11；依賴 pyyaml、jsonschema、certifi；開發依賴 pytest）、`config/settings.yaml`、`pipeline/` 套件。
- `pipeline/tokenizer.py`：逐字元狀態機的單行 tokenizer。`pipeline/parse.py`：事件序列、台上立繪追蹤、schema 驗證。`pipeline/gamedata.py`：下載與場景索引。`pipeline/casting.py`：說話者統計。`pipeline/schemas/timeline.schema.json`。
- 三個子命令（`--scene` 省略時處理整個活動，預設 act33side）：

```
python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pipeline fetch-gamedata            # → data/gamedata/{excel,story}/，有快取就跳過
.venv/bin/python -m pipeline parse --scene act33side_st01   # → out/act33side_st01/timeline.json
.venv/bin/python -m pipeline parse                     # 23 場
.venv/bin/python -m pipeline speakers                  # → out/act33side/speakers.csv
.venv/bin/python -m pytest
```

### 驗收結果
- 23 場全部解析，無例外、無未知指令、無解析失敗的行；每份 timeline 寫檔前都通過 schema。31 個測試全過。
- 規劃口徑（`[name=...]` 行＋非 `[` 開頭的非空行）：BB-ST-1 = 127（對白 89＋旁白 38）；全巴別塔 = 4400，旁白 761，博士 467。與 `docs/00-decisions.md` 完全一致。
- `speakers.csv`：103 個有名字的說話者（另有「（旁白）」「（字幕）」兩列）。與規劃的 104 差 1，推測規劃把旁白算成一個說話者。
- 指令頻次與規劃一致，只有 background 是 213（規劃寫 194）、dialog 合計 713（566＋147，一致）。

### 口徑差異：timeline 的句數比規劃口徑多
全巴別塔 timeline 共 4547 句 = 規劃口徑 4400 ＋ 帶文字的 Subtitle 124 句 ＋ multiline 23 句。這 147 句規劃時沒算進去，但都是畫面上會出現的文字，依「所有文本都要配音」應該配音。BB-ST-1 因此是 144 句（127＋17 句字幕）。每份 timeline 的 `stats` 同時列出兩種數字。

### 自行決定的技術細節
- **multiline 不合併**：同一區塊的各段之間常夾著立繪切換、震動、音效指令，合併會打亂事件順序。每段各自是一個 line，帶 `multiline: {block, end}`；同 `block` 的各段在同一個對話框接續顯示。有的區塊沒寫 `end=true`，由下一個 `[dialog]` 或 `[name=...]` 收尾。若日後想把同一區塊合成一段語音，按 `block` 分組即可。
- **契約之外新增的欄位**（已寫進 `docs/01-architecture.md` 檔尾與 schema）：line 的 `focus_group`、`rich_text`、`multiline`、`args`；頂層的 `header`、`stats`。所有 line（含旁白、字幕）都帶 `sprites_on_stage`、`tts_text`、`emotion`。
- **focus_group**：被打亮的立繪組，是判斷「這句是誰說的」最直接的線索。`focus` 明示 l/m/r 取該位置；明示 n（全暗，說話者不在台上）為 null；未指定時台上恰好一個立繪就取它，否則 null。巴別塔 3662 句對白中 2988 句有值；其餘 674 句裡 572 句是台上沒有立繪。
- **台上立繪的規則**：`[charslot]` 無 slot（含只有 duration）＝清空；有 slot 無 name ＝不換人只改焦點或做動作；`name="char_empty"` 或 `ato=0`（淡出到全透明）＝該位置清空；slot 與 focus 的 `left/right/none` 視同 `l/r/n`（腳本兩種寫法混用，args 裡保留原樣）。`charactercutin` 的立繪也算在台上，排在 charslot 之後。
- **文字清理**：line 的 `text` 去掉 `<color=...>` 等富文本標籤，`{@nickname}` 代入 `settings.yaml` 的 `doctor_nickname`（博士）；原文不同時另存 `rich_text` 給渲染器。星號舞台提示（`*萨卡兹粗口*`）不動，留給填 `tts_text` 的階段。Sticker 的 text 是指令參數，保留原樣含標籤。
- **參數**：鍵一律小寫（`widgetID` → `widgetid`）；只有未加引號的值才轉型，加引號的數字保持字串（`widgetID="1"`）。腳本不轉義引號，所以引號內的值以「後面緊接 `,` `)` `]` 或行尾的引號」為結尾。
- `[HEADER(...)]` 不產生事件，參數放在頂層 `header`。`[Decision(options=..., values=...)]` 的兩個參數以 `;` 拆成陣列。帶文字的 `[Subtitle]` 是 `kind: subtitle` 的 line（座標等參數在 `args`）；無參數的 `[subtitle]` 是清除指令，保留為 `cmd: subtitle`。
- 以 `[` 開頭但解析失敗的行：`cmd: _unparsed`，附 `raw`、`error`、`src_line`。巴別塔沒有這種行。
- 下載用 certifi 的根憑證：python.org 版的 macOS Python 不帶系統憑證，直接下載會憑證驗證失敗。
- `data/gamedata/` 目錄佈局照 Kengxxiao 倉庫：`excel/<表>.json`、`story/activities/act33side/level_*.txt`。主工作目錄裡別的 session 留下的 `data/excel/`、`data/story/` 是另一套佈局，本管線不讀。

### 留給下一個 session 的問題
1. **Decision 選項沒有配音**：巴別塔有 5 個 `[Decision]`，選項是博士的台詞（如「我相信它们。相信你，凯尔希。」），目前只是普通指令事件，不是 line。要不要配音由專案擁有者或導演表階段決定；要配的話在 `parse.py` 把它改發成 `kind: dialogue`、speaker 博士的 line 即可。
2. **字幕（124 句）沒有說話者**：有的是孩子們的話、有的是老師講課、有的是博士的內心獨白，身份要靠上下文判斷，屬於身份表（`identity-table`）的範圍。
3. `docs/00-decisions.md` 寫 BB-ST-1 有「14 個立繪名」；實測是 21 個不同的立繪名（含表情變體）、8 個立繪組（凯尔希、阿斯卡纶、5 個 NPC、npc_10002）。4 張背景相符。素材下載（S2）以 timeline 為準。
4. 舊語法 `[character(name=, name2=, focus=)]` 已支持並有測試，但巴別塔沒有實例，未用真實腳本驗證過。
