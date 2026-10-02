# S0 SCRP 叢集偵察

## 目標
確認 `docs/03-scrp-cluster.md` 的 6 個待確認項，產出 `cluster/ENV.md`（事實清單）與可用的 `cluster/setup_env.sh` 初稿。

## 前提
使用者在 Mac 上開 session，並能 `ssh <id>@scrp-login.econ.cuhk.edu.hk`（可能需 CUHK VPN）。Claude 透過 Bash 執行 ssh 命令；若互動式密碼提示阻塞，請使用者先設 ssh key 或在旁輸入密碼。

## 步驟
1. 登入節點：`qos`、`scrp-quota`、`scrp-info`、`conda info --envs`、`module avail 2>&1 | head -50`、`which ffmpeg apptainer`、`nvidia-smi`（登入節點可能無 GPU）。
2. 計算節點外網：`compute -t 10 bash -c 'curl -sI https://huggingface.co | head -1; curl -sI https://github.com | head -1; nvidia-smi'`；若排隊久改 `gpu -t 10 ...`。
3. 磁碟：`df -h ~ ~/large-data`；確認 `~/large-data` 存在並可寫。
4. 建環境方案判定：
   - 計算節點有外網 → 一切在 sbatch 內 pip install；
   - 無外網 → 登入節點用 `screen` 建 conda 環境與下載權重（注意 4 核 4 GB 與 24 h 限制）。
5. 寫 `cluster/setup_env.sh`（conda env 放 `~/large-data/conda/envs/aktts`，Python 3.10/3.11，torch 版本對應驅動 CUDA 版本，`pip install indextts`（或 git clone index-tts）、`funasr`、`soundfile`、`pyyaml`），先只做到「import 成功、`torch.cuda.is_available()` 為 True」。
6. 寫 `cluster/ENV.md`。

## 驗收
- `cluster/ENV.md` 回答全部 6 個待確認項，含命令輸出摘錄。
- 在一張 3090 上 `python -c "import torch; print(torch.cuda.get_device_name())"` 成功。
- 不下載任何遊戲資料到叢集（還沒到那步）。

## 邊界
- 不修改使用者 `~/.bashrc` 以外的全局設定；conda `envs_dirs` 改動寫在 `~/.condarc` 並記錄。
- 不要申請額外配額；若 QoS 只有 1 GPU 1 天，記錄即可，足夠一章推理。

## 完成記錄
（session 結束時填寫）
