# SB 參考音目錄：替每個可克隆的幹員備好參考音

寫給一個全新的 Claude Code session（Mac ＋ SCRP 叢集）。
開始前讀：`docs/00-decisions.md`（含全部追加記錄）、`cluster/ENV.md` 的「追加測試五、七、十、十一」與「追加測試六」（SSH 與 VPN 並存的現況）。

## 為什麼要做
已定案的合成做法（專案擁有者聽審後認可）：引擎 IndexTTS-2；參考音**逐句依上下文挑**，直接當音色參考音；情緒用文字描述、強度 0.3。
要逐句挑，每個角色就得先有一份「可選的參考音清單」。凯尔希的已做過（`cluster/ref_catalog.py` 逐句量測、`cluster/round2.py` 的 `segments` 把長句切成 3–10 秒片段、拼接短句），但腳本寫死了凯尔希。本任務把它變成通用工具並替所有可克隆的角色跑完。

## 角色清單（巴別塔中有中文語音的幹員；句數是劇本顯示名的粗估）
凯尔希 `char_003_kalts`（241，已有目錄，重跑以統一格式）、特蕾西娅＝魔王 `char_4134_cetsyr`（680）、阿斯卡纶 `char_4132_ascln`（244）、阿米娅 `char_002_amiya`（128）、奥达 `char_4131_odda`（77）、暴行（43）、可露希尔（37）、Mantra＝真言 `char_4204_mantra`（19）、Pith（18）、W `char_113_cqbw`（12）、Logos＝逻各斯 `char_4133_logos`、Mon3tr、伊内丝、赫德雷、Stormeye、Mechanist＝机械师。
沒寫 charId 的請自行查 `character_table.json`；清單以另一個 session（SA 身份表）的 `config/identity/speakers.yaml` 為準，若它還沒出來就先用上面這份，並在完成記錄註明。

## 產出
1. 通用腳本（取代寫死凯尔希的版本，放 `cluster/`）：`python ref_catalog.py <短名> <charId> <顯示名>` 一次完成：下載該幹員全部中文語音（`PseudoMon/arknights-audio` 的 `voice_cn/<charId>/`）→ 逐句量測（語速、停頓、音高、起伏、頻譜質心、emotion2vec 情緒分數）→ 長句按停頓切成 3–10 秒片段並用語音辨識回檢文字對齊 → 把短於 3 秒的句子依量測拼接成可用片段 → 輸出 `refs.json` 與一張試聽頁。
2. 叢集上每個角色一個目錄 `~/large-data/aktts/work/refs/<短名>/`（音檔、`catalog.json`、`refs.json`、`catalog.html`）。
3. 入庫的目錄摘要 `config/refs/<短名>.json`：每段參考音的 id、來源語音編號、長度、量測值、情緒分數、是否可用。**不含台詞原文與音檔**（版權，D16）；需要文字時用語音編號回查。
4. `cluster/ENV.md` 追加一節：每個角色的語音句數、可用參考音段數、各情緒類別的段數、有哪些語氣完全沒有樣本。
5. 在本檔底部填「完成記錄」。

## 已知的坑（都寫在 `cluster/ENV.md`）
- 經 SSH 提交作業：`ssh scrp`（金鑰已設）。**不要高頻探測**，另一個 session 曾因每 5 秒連一次被叢集封鎖約一小時；輪詢間隔 ≥ 60 秒，並用 `ControlMaster` 重用連線。
- 作業腳本用 `#!/usr/bin/env bash` 的檔案提交，不要用 `sbatch --wrap`（那是 sh，沒有 `source`）。開頭 `source ~/large-data/aktts/env.sh`。
- 3090 節點記憶體常被佔滿：`--partition=scrp,gpu`、`--mem` 保守。
- 切片的時間對齊是「字數比例＋最近停頓」，不是逐字對齊；對齊字錯率 > 0.15 的片段標為不可用。若有餘力可改用 FunASR 的時間戳做逐字對齊。
- emotion2vec 的標籤對凯尔希偏差明顯（冷峻語氣被標成「生气」），只能當分群線索，不能當情緒真值。專案擁有者表示自己分辨不了情緒，**不要把聽審情緒的工作交給他**。

## 驗收
- 清單上每個角色都有 `refs.json`；每個角色可用參考音 ≥ 6 段，不足的寫明原因。
- 入庫檔不含台詞原文、不含音檔。
- 腳本對任一角色可重跑、結果一致。

## 邊界
- 不做合成、不挑逐句參考音（那是之後「導演表」的事）。
- 不上傳任何聲優音訊到 ElevenLabs 或其他外部服務（D3 與風險表）。

## 完成記錄
（session 結束時填寫）
