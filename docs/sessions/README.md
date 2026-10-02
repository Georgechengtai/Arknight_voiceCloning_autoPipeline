# Session 任務書索引

每份任務書都寫給一個**全新的 Claude Code session**（在使用者的 Mac 上執行，S0/S4 另需 SSH 到 SCRP）。
開始任何 session 前先讀：`docs/00-decisions.md`、`docs/01-architecture.md`、`docs/02-data-sources.md`，以及本目錄中該 session 的文件。

| 序 | 任務 | 執行位置 | 依賴 | 需要使用者參與 |
|---|---|---|---|---|
| S0 | SCRP 叢集偵察 | Mac → ssh SCRP | 無 | 提供帳號、在旁執行 ssh |
| S1 | 專案骨架＋腳本解析器＋timeline | Mac | 無 | 否 |
| S2 | PRTS 素材解析與下載器 | Mac | S1 的 timeline | 否 |
| S3 | 選角表、參考音、ElevenLabs 聲線設計 | Mac | S1 | **是**：聽審並挑選聲線 |
| S4 | SCRP 端 TTS 批次＋ASR 質檢 | SCRP | S0、S3 的 manifest | 否（跑完回報 flag 清單） |
| S5 | HTML/Canvas 渲染器＋Playwright＋ffmpeg | Mac | S1、S2（S4 的音訊可先用 TTS 佔位） | 否 |
| S6 | BB-ST-1 端到端整合、聽審、投稿檢查表 | Mac | S1–S5 | **是**：最終審片 |

S1、S2、S3、S5 可並行（S2/S3/S5 以 S1 定義的 timeline 契約為介面，契約已寫在 `docs/01-architecture.md`）。
S0 隨時可做。S4 在 S0 與 S3 之後。S6 最後。

共同規則：
- 不把遊戲素材、原聲、生成音訊/影片提交到 git（`.gitignore` 已設）。
- 每個 session 結束時更新對應任務書底部的「完成記錄」，寫下實際做了什麼、偏離設計之處、留給下一個 session 的問題。
- 遇到需要使用者決定的「邊界問題」（版權、平台規則、聲線取捨、叢集權限）用 AskUserQuestion 問；純技術細節自行決定並記錄。
