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

完成日期：2026-10-02。產出：`cluster/ENV.md`（6 個待確認項全部回答，附命令輸出）、`cluster/setup_env.sh`（已在叢集實跑成功）。

### 實際結果

| 待確認項 | 結果 |
|---|---|
| 1. 配額與分區 | 帳號屬 `teachers`，預設配額 `c32g8`：單一作業最長 5 天，最多 4 張 RTX 3090（合計 8 張 GPU、128 核、512 GB） |
| 2. 計算節點外網 | 有。HuggingFace、GitHub、PyPI、PyTorch 下載站、hf-mirror、ModelScope 全通，無需代理 |
| 3. 磁碟 | `~/` 50 GB；`~/large-data` 上限 1.95 TiB 但看起來雙倍計量，實際約 1 TB；conda 環境與快取已指向 `~/large-data`（寫在 `~/.condarc`） |
| 4. GPU 驅動 | 580.65.06（支援到 CUDA 13.0）；採用 torch 2.8.0+cu128，不需 `module load cuda` |
| 5. 長時間佔用 | 允許（5 天上限）；真正的排隊瓶頸是 3090 節點的記憶體，作業請用 `--partition=scrp,gpu` 且 `--mem` 保守 |
| 6. ffmpeg | 登入節點與計算節點都沒有；符合原設計（叢集只寫 WAV） |

驗收：
- `cluster/ENV.md` 回答全部 6 項並附輸出摘錄 ✔
- 在 RTX 3090（`scrp-node-9`）上 `torch.cuda.is_available()` 為 True、`torch.cuda.get_device_name()` 回傳 `NVIDIA GeForce RTX 3090` ✔（安裝作業 407395，另以全新作業 407400 經 `env.sh` 再驗一次）
- 沒有下載任何遊戲資料到叢集 ✔（也沒有下載模型權重）

### 偏離任務書之處

1. **沒有用 SSH**。SCRP 的 SSH 從校外連線逾時（須校園網或 CUHK VPN），而使用者的 Mac 必須開著 Private Internet Access 才能連 Claude、尚未安裝 CUHK VPN。改為：使用者在瀏覽器登入 SCRP JupyterHub（校外可直連），Claude 透過 JupyterHub 的終端機介面執行全部命令、透過其檔案介面上傳 `setup_env.sh`。
2. 仍按使用者的選擇準備了 SSH 金鑰：Mac 端 `~/.ssh/id_ed25519_scrp` 與 `~/.ssh/config` 別名 `scrp` / `scrp2`；叢集端公鑰已加入 `~/.ssh/authorized_keys`。**因為 SSH 不通，這把金鑰尚未實際登入測試過。**
3. 安裝方式不是任務書寫的 `pip install indextts`，而是 `git clone` 官方倉庫後用它的 `uv.lock`（`uv sync`）裝進 conda 環境，版本完全按上游鎖定；Python 選 3.11。
4. 第 2 步的探測命令加了 `--gpus=rtx3090 -c 2 --mem=8G`，以確保是在 3090 節點上量測。
5. 第一次安裝作業（407391）失敗：IndexTTS 的 `.python-version` 釘死 3.11.13，`uv` 拒用 conda 環境。修正腳本後第二次（407395）成功，耗時 5 分 37 秒。失敗那次在 `~/.local/share/uv/` 留下 94 MB 沒用到的 Python，未刪（見 `cluster/ENV.md`「對叢集做的改動」）。

### 追加（同日，應專案擁有者要求，超出原任務書範圍）

1. **CUHK VPN 並存測試：失敗。** 使用者安裝 GlobalProtect 並在 Private Internet Access 開著時連上，Mac 立刻全面斷網，SSH 仍不通；斷開後恢復。原因（路由被搶、DNS 被換）與證據見 `cluster/ENV.md`「追加測試一」。
2. **IndexTTS-2 與 2.5 對比：兩版都合成成功。** 下載了兩套權重（各 11 GB）到叢集，各合成 8 句。2.5 版較快（每秒音訊 0.726 秒對 1.009 秒）、較省顯示記憶體（5.33 GB 對 8.82 GB）。音質尚待專案擁有者試聽。腳本 `cluster/ab_indextts.sh`、`cluster/ab_indextts.py`，數據見 `cluster/ENV.md`「追加測試二」。

3. **專案擁有者否定了第 2 項的參考價值**（參考音只有 2 秒且是喊叫、又不是原著語音），要求改用原著語音。於是做了第三輪：下載凯尔希、阿斯卡纶的中文原聲共 20 個檔到叢集，用平穩的交談語音當參考音，合成「同文對比」與 BB-ST-1 真實台詞共 22 條 × 2 版，並算聲紋相似度與字錯率。結果：平穩語句音色接近上限；情緒向量會讓音色跑掉；IndexTTS-2.5 有兩句長台詞輸出失控而 IndexTTS-2 正常。腳本 `cluster/real_ab.sh`、`cluster/real_ab.py`，數據與限制見 `cluster/ENV.md`「追加測試三」。**這一步把遊戲原聲下載到了叢集，超出原任務書「不下載任何遊戲資料到叢集」的驗收條件，是應專案擁有者要求。**
4. **未執行：ElevenLabs 克隆基準。** 專案擁有者提出把角色語音放進 ElevenLabs 克隆作為基準；Claude 沒有做，理由見 `cluster/ENV.md`「追加測試三」末段。

5. **專案擁有者聽完第三輪後認為不微調效果很差，並指出 IndexTTS 只用一段參考音、浪費整池語音**（查原始碼屬實）。於是做了第四輪：在叢集另建環境安裝 GPT-SoVITS，用凯尔希 36 句原聲（4.51 分鐘）微調，約 4 分鐘訓練完，合成同一批台詞。結果：微調讓 GPT-SoVITS 的聲紋相似度從 0.788 升到 0.844，但與不微調的 IndexTTS-2（0.840）基本打平；英文詞「Monster」念得比 IndexTTS 差。音質與語氣待專案擁有者試聽。安裝過程踩了 8 個坑，都已寫進 `cluster/gsv_finetune.sh`。詳見 `cluster/ENV.md`「追加測試四」。
6. **GlobalProtect 會自己重連**（又讓 Mac 斷網兩次），其中一次意外證實 SSH 金鑰登入可行，並存只差 DNS 一個問題。專案擁有者決定另開 session 處理，任務書 `docs/sessions/S0b-vpn-coexistence.md`，監測腳本 `tools/vpn_monitor.sh`。

### 留給下一個 session 的問題

1. **Mac 與叢集之間怎麼傳檔**（影響設計決定 D4、`docs/01-architecture.md` 的 `pipeline cluster push/pull`、S4 步驟 4）：校外 SSH/rsync 不通，CUHK VPN 又無法與 Private Internet Access 並存。待專案擁有者決定：走 JupyterHub 的 HTTPS 介面（S0 已驗證可傳檔、提交作業、取結果；全自動化需要存取權杖，未驗證）／只在校園網用 SSH／改 Private Internet Access 設定求並存（未嘗試）。S4 開工前要先定案。
2. **IndexTTS 用 2 還是 2.5**（設計決定 D3 寫的是 IndexTTS-2）：客觀數字偏向 IndexTTS-2（2.5 版有兩句長台詞失控），待專案擁有者試聽第三輪的試聽頁後決定。連帶要定：情緒怎麼給（設計決定 D13「第一版不控情緒」在情緒激烈的場景是否成立）、設計決定 D12 的回檢要先做同音字歸一。
3. 一章的推理時間原估 1–2 小時偏樂觀；以實測速度粗估單張 3090 上限約 4 小時，可拆成多個作業並行。
4. 未安裝加速選項（flash-attn、DeepSpeed、ninja）；S4 再評估。
5. 叢集上有管理員預裝的 `omnivoice` conda 環境（另一個語音合成工具），不在設計內，僅記錄。
