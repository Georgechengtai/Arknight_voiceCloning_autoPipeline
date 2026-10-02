# 03 SCRP 叢集（中大經濟系 HPC）已知事實與待確認項

來源：https://scrp.econ.cuhk.edu.hk 的 about、guide/slurm、guide/python、guide/storage、guide/singularity、guide/modules、guide/account-and-access（2026-10-02 抓取）。

## 已知事實

- 登入：`ssh <CUHK Compute ID>@scrp-login.econ.cuhk.edu.hk`（或 `scrp-login-2`）。檔案傳輸用 scp/rsync/WinSCP。JupyterHub：`https://scrp-login.econ.cuhk.edu.hk/jupyter`。
- 排程：Slurm。簡易封裝命令：
  - `compute -c 8 --mem=40G --gpus=rtx3090 -t 1-0 python script.py`（互動/前台）
  - `gpu python script.py`（任意一張 GPU）
  - `sbatch job.sh`（背景；`#SBATCH --gpus=rtx3090` 等）
  - `compute -z ...` 印出底層 srun 命令。
- GPU：RTX 3090 ×11（node-8/9 各 4、node-10 2、node-22 2）、RTX 3060 ×20、A100/A800（a100 分區限教師與研究生）。RTX 3090 自動配 8 核 48 GB RAM。
- 配額（QoS，用 `qos` 命令查）：c4g1 = 4 核 1 GPU 1 天；c16g1 = 16 核 1 GPU 5 天；研究生 128 核 4 GPU；本科/授課型碩士 16 核 1 GPU 5 天。預設時限 scrp 分區 1 天。
- 軟體：conda 預裝環境 `pytorch`（PyTorch 2.12）、`anaconda`、`base`；可 `conda create -n <name>`；`module load cuda/12.x`（有 11.7 ~ 13.3）；Apptainer 1.5（`gpu apptainer shell --nv image`）。
- 儲存：`~/` 2/20/50 GB（本科/研究生/教師，有備份）；`~/large-data` 20/500/1000 GB（高速、無備份，**模型權重與生成音訊放這**）；`~/archive`；`/tmp` 節點本地。`scrp-quota` 查用量。
- 登入節點限 4 核 4 GB，> 24 h 的進程會被殺；下載模型權重（數 GB）在登入節點做可以，但解壓/轉檔放計算節點。

## 待確認（S0 偵察）

1. 使用者的 QoS 與分區（學生還是研究生級）→ 單次作業最長時間、能否同時用 1 張以上 GPU。
2. 計算節點是否能連外網（HuggingFace / GitHub）。文件提到 Apptainer 可用 URL 拉映像，暗示可以，但要實測 `curl -I https://huggingface.co` 於 `compute` 內。
3. `~/large-data` 實際配額；conda 建環境預設放 `~/`（20 GB 可能不夠），需設 `conda config --add envs_dirs ~/large-data/conda/envs` 與 `pkgs_dirs`。
4. GPU 節點的 CUDA 驅動版本（`nvidia-smi`）以選 torch 版本。
5. 是否允許長時間佔用（一章 4400 句約 1–2 小時推理，遠低於 1 天上限，應無問題）。
6. ffmpeg 是否預裝（渲染在 Mac 做，叢集只需 soundfile/torchaudio 寫 WAV，不依賴 ffmpeg）。
