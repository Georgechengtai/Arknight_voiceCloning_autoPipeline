# Arknights 劇情 AI 配音自動管線（Arknight_voiceCloning_autoPipeline）

把《明日方舟》劇情腳本（Kengxxiao/ArknightsGameData 的 story txt）自動變成
「原版背景＋立繪＋BGM＋音效＋AI 克隆語音」的 MP4，發佈到 bilibili（非盈利同人）。

目前狀態：**已有 BB-ST-1 / BB-1 配音產物，2026-10-23 搬遷至校園工作電腦主控、SCRP 執行。** 接手請先讀 [校園交接文件](docs/migration/CAMPUS-HANDOFF.md)。所有決定及歷史見 `docs/`。

| 文件 | 內容 |
|---|---|
| `docs/00-decisions.md` | 可行性結論、每個設計決定及理由、風險 |
| `docs/01-architecture.md` | 管線階段、資料契約（timeline / manifest / casting）、目錄規範、Mac 與 SCRP 分工 |
| `docs/02-data-sources.md` | 所有外部資料來源的核實結果：URL、鍵名格式、覆蓋率、限速 |
| `docs/03-scrp-cluster.md` | 部門 GPU 叢集（SCRP）已知事實與待確認項 |
| `docs/sessions/S0…S6` | 拆分成 7 個可獨立執行的 Claude Code session 任務書 |

執行環境：校園工作電腦主控；SCRP 跑 GPU 任務，沿用工作電腦既有內網連線及 Chat API 設定。Mac 不再是生產環境。

第一個里程碑：巴別塔（act33side）幕間 **BB-ST-1「未完成的告别」**（127 行）全流程跑通。
