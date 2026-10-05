# SC 把 BB-ST-1 的配音整理成逐句檔與語音清單

## 背景
BB-ST-1 的配音已經做完、專案擁有者聽過六版並認可（`docs/00-decisions.md` 2026-10-05 各節必讀）。但現在的成品是「一條音軌＋分段時間」，做影片需要**逐句**的音檔與時間。這個 session 只做整理與檢查，**不重新合成、不改任何一句的聲音**。

## 現有的東西（都在主倉庫的 `out/act33side_st01/`，worktree 裡的 `out` 是連到那裡的捷徑）
- `lines.json`：158 行的播放順序、身份、原文（`tools/scene_lines.py` 產生）。
- `director_el.json`：ElevenLabs 的 38 段（`first`/`last` 是段的起訖行、`prompt` 是送出的文字含語氣標記、`gap_before`）；音檔 `el/<block>.mp3`。
- `director_idx.json`：幹員 34 句的導演表；音檔 `idx/<line_id>.wav`（已是逐句）。
- `cues.json`、`scene.mp3`：`tools/scene_assemble.py` 接出來的整場音軌與分段時間（專案擁有者認可的就是這個的聽感）。

## 要交付的
1. `out/act33side_st01/voice/<line_id>.wav` 與 `out/act33side_st01/voice_manifest.json`，格式見 `docs/01-architecture.md`「追加 2026-10-05」。158 行每行一筆。
2. `tools/voice_manifest.py`（或併進 `pipeline/`）：從上面的輸入可重跑地產生第 1 項。
3. ElevenLabs 那 38 段的回聽比對結果：哪幾段有漏字、多字、念錯（之前只查過語速）。有問題的列清單，不要自行重做。
4. 驗收用的檢查：把 `voice/` 的逐句檔照清單的間隔規則重新接成一條音軌，與現有 `scene.mp3` 比總長（差距應在 2 秒內）；每個逐句檔的句尾音量低於峰值 -45 dB（沒有被切在聲音上）。

## 怎麼切 ElevenLabs 的段
- 需要語音辨識的逐字時間。叢集上有 FunASR（`paraformer-zh` 會回傳逐字時間）；`cluster/scene_variants.py` 的 `align()` 與「在兩句之間挑最安靜的 20 毫秒」那段可以直接搬來用。把 38 個 mp3 傳上叢集、跑一支只做辨識與切點的作業、取回切點即可（音檔是自己生成的，可以上傳到叢集；**不可上傳到任何外部服務**）。
- 叢集連線規則見 `cluster/ENV.md`：SSH 輪詢間隔 ≥ 60 秒、用 ControlMaster；CUHK VPN 只有專案擁有者人在 Mac 前時才連得上，連不上就先做不需要叢集的部分並回報。
- 段內的語氣標記（`[pause]`、`[coughs]` 等）會產生停頓與非語言聲音：咳嗽、喘息要歸給它所屬的那一句，不要切掉。原文是「咳。」而送出去的是 `[coughs]` 的地方，辨識結果不會有字，切點要靠前後句推。
- 切完的每句：去頭去尾、句尾留 0.08 秒並淡出 0.06 秒、統一音量（做法照 `tools/scene_assemble.py`）。段內兩句之間原本的停頓長度要記到下一句的 `gap_before`（專案擁有者認可的是 ElevenLabs 自己的段內節奏，不要改成預設的 0.8 秒）。

## 邊界
- 不重新生成任何音檔、不換聲線、不改導演表的內容。發現問題只記錄。
- 不做背景音樂與音效。
- 遊戲文本與音檔不入庫（`out/` 已忽略）；清單裡不要放完整台詞。

## 完成記錄
（session 結束時填寫）
