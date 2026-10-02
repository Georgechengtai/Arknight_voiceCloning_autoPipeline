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
（session 結束時填寫）
