# 巴別塔：校園工作電腦接手（2026-10-23）

## 新的執行安排
使用者決定：校園工作電腦是主控端，SCRP 是 GPU 與既有 Chat API 執行端。
MacBook 不再負責後續製作，不需要重設雙 VPN。工作電腦的 SCRP 存取已由使用者設定好；沿用它，切勿搬運 Mac 私鑰或覆寫既有連線設定。

程式 repo：https://github.com/Georgechengtai/Arknight_voiceCloning_autoPipeline
完整私人備份：https://github.com/Georgechengtai/Arknight-voice-migration-private/releases/tag/campus-migration-2026-10-23

私人 Release 包含當次程式快照、所有本機 data/assets/out、歷次試音及影片、導演表、日誌、舊 worktree 來源檔、全部本機 Git refs 的 bundle，以及逐檔 SHA-256 manifest。
不搬運可重建的虛擬環境、快取、Git worktree 管理指標、憑證。精確排除清單見 manifest.json。
原有 SCRP 上的模型、參考音及環境不是 Mac 資料；保留在原有 ~/large-data/aktts，未在此備份或重新驗證。

## 工作電腦恢復
建議 Windows 用 WSL2/Linux；既有 Linux 可直接做。需要 Git、GitHub CLI、Python 3.12+。
下載、暫存 tar、解壓三者合計請預留至少 25 GB。用有私人 repo 權限的 GitHub 帳號登入。

```bash
gh auth login
mkdir -p ~/babel-transfer
cd ~/babel-transfer
gh release download campus-migration-2026-10-23 --repo Georgechengtai/Arknight-voice-migration-private
sha256sum -c SHA256SUMS
python3 archive.py restore . ~/Arknight_voiceCloning_autoPipeline
cd ~/Arknight_voiceCloning_autoPipeline
```

恢復腳本先核對每件附件及每個封存檔案，然後解壓到空目錄；不覆寫既有工作。
連結會改成可攜的相對連結。`.claude/worktrees/` 是歷史救援副本，不是可繼續操作的 Git worktree。

```bash
git init
git fetch migration-history.bundle 'refs/heads/*:refs/remotes/snapshot/*'
git symbolic-ref HEAD refs/heads/campus-migration
git reset --mixed refs/remotes/snapshot/codex/campus-migration-2026-10-23
git remote add origin https://github.com/Georgechengtai/Arknight_voiceCloning_autoPipeline.git
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,render]'
python -m playwright install chromium
python -m pytest -q
```

另安裝 ffmpeg、Noto Sans CJK SC 字型及 Playwright 所需系統套件。不要複製 Mac .venv。
確認 `git status`；快照中的未提交檔不應被清除。

## SCRP 接手檢查（只在校園工作電腦做）
1. 使用既有 SSH alias；現有工具用 `scrp`，若工作電腦用別名，新增等價 alias，不覆寫既有設定。
2. 一次連線檢查 `~/large-data/aktts/env.sh`、`work/refs`、IndexTTS 權重；用 `sinfo` / `sacctmgr` / `df` 查當前資源。2026-10-02 配額只是歷史證據。
3. 既有 Chat API 認證沿用工作電腦安全設定；不要寫入 GitHub。
4. 不自動同步舊 Mac 的整個 cluster 目錄到 SCRP，避免蓋掉那邊較新的程式。先比較版本。
5. 高耗時工作用 Slurm；SSH 重用連線，輪詢至少 60 秒。主控在工作電腦、模型與 GPU 任務在 SCRP。

## 製作狀態與不可丟失的決策
先讀 docs/00-decisions.md，後追加的決策優先。README 原本「尚未開工」已過時。
BB-ST-1、BB-1 行動前後都有聲音產物。out 內 director_el.json、director_idx.json、voice_manifest.json 是重要製作資料，不能因為被 gitignore 就省略。
ElevenLabs 使用 v4，原創 Voice Design，不傳角色原聲。旁白用說書人口吻；同場對話照對方上一句反應。
曼弗雷德最終 voice_id：Z0VKUGVdUkEzqVWbvvdF；尤莉葉成熟版：EZJp3qpLzzCerITHj2Xp。
已核實聲線列表見 config/elevenlabs-verified-voices.json（2026-10-09，工作電腦需重新連接帳號）。
IndexTTS-2 為現有基準；Fish Drama 3 僅為候選，先 A/B 測試，不批量替換已認可聲音。
有些身份標記與參考音目錄不一致，例如 Pith；先建立最終 engine routing，不能只靠 role=npc 決定 ElevenLabs。

## 接手後第一個任務
驗證恢復結果與 SCRP 既有參考音，抽聽已認可版本，然後執行 FISH-DRAMA3-EVALUATION.md。
完整恢復前不要刪 Mac 原件；本次只搬遷，不刪除本機。這不是要求日後繼續在 Mac 生產。
