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

## 2026-10-04 更新：目前可同時進行的三個 session

原計畫一次排了七個 session，結果卡在 S0。現在只開彼此不相依、馬上能做的三個，各自在自己的 worktree（`.claude/worktrees/<名稱>`，分支同名）裡工作，做完再合回 master。

| worktree／分支 | 任務書 | 做什麼 | 用到叢集 | 需要專案擁有者 |
|---|---|---|---|---|
| `s1-parser` | `S1-parser-timeline.md` | 專案骨架、腳本解析器、timeline.json（原計畫不變） | 否 | 否 |
| `identity-table` | `SA-identity-table.md` | 每一句到底是誰在說；劇本名字與幹員的對應 | 否 | 看一份附上下文的待確認清單 |
| `ref-catalogs` | `SB-ref-catalogs.md` | 替每個可克隆的幹員備好參考音清單 | 是 | 否 |

三者之後匯合成下一步（尚未開 session）：導演表（逐句挑參考音與情緒描述）→ 合成與自動質檢 → 抽查。無原聲角色的 ElevenLabs 選角（原 S3）與渲染器（原 S5）等這三個有結果再排。

S0 與 S0b 已完成。已定案的合成做法與各項決定見 `docs/00-decisions.md` 的追加記錄。

合併時注意：`cluster/ENV.md` 與 `docs/00-decisions.md` 多個 session 都會追加，請只在檔尾加新的一節，不要改寫既有內容。

## 2026-10-05 更新：第一支完整影片（BB-ST-1）要開的三個 session

BB-ST-1 的配音已完成並經專案擁有者認可（六版，見 `docs/00-decisions.md`）。上面三個 session（`s1-parser`、`identity-table`、`ref-catalogs`）都已合併。現在開三個彼此不相依的，各自一個 worktree，做完合回 master，再由整合 session（S6）出片。

| worktree／分支 | 任務書 | 做什麼 | 用到叢集 | 需要專案擁有者 |
|---|---|---|---|---|
| `assets` | `S2-prts-assets.md`（含文末補充） | 下載 BB-ST-1 的背景、立繪、插圖、BGM、音效，產出素材清單 | 否 | 否 |
| `renderer` | `S5-renderer.md`（含文末補充） | 時間表、畫面渲染、逐幀截圖、混音出片 | 否 | 否 |
| `voice-lines` | `SC-voice-lines.md` | 把現有配音切成逐句檔、產出語音清單、回聽比對 ElevenLabs 的段落 | 是 | CUHK VPN 要他人在 Mac 前才連得上 |

三者的介面：`out/<scene>/timeline.json`（已有）、`out/<scene>/assets_manifest.json`（`assets` 產出）、`out/<scene>/voice_manifest.json`（`voice-lines` 產出）。`renderer` 在另外兩份還沒出來時用佔位資料開發。

每個 worktree 裡的 `out`、`data`、`assets`、`.venv` 是連到主倉庫同名目錄的捷徑（已列入 `.git/info/exclude`），所以三個 session 看到的是同一份資料，產出也直接落在主倉庫。**不要刪除或覆蓋 `out/act33side_st01/` 裡既有的檔案**（那是認可過的成品與各版本的音檔），只新增。

合併時注意同上：`docs/00-decisions.md`、`docs/01-architecture.md`、`cluster/ENV.md` 只在檔尾加新的一節。
