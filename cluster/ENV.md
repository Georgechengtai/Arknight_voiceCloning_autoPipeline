# SCRP 叢集環境事實清單（S0 偵察結果）

偵察日期：2026-10-02（叢集時間 20:44–21:05）。帳號：`georgecheng`。
本文件回答 `docs/03-scrp-cluster.md`「待確認」的 6 個問題，並記錄偵察中發現、會影響後續 session（尤其 S4 叢集 TTS 批次）的事實。
所有結論都附當時的命令輸出摘錄；與 `docs/03` 的「已知事實」不一致之處以本文件為準。

## 一句話總結

- 帳號是**教師級**配額：單一作業最長 5 天，可同時用最多 4 張 RTX 3090。
- 計算節點**有外網**（HuggingFace、GitHub、PyPI、PyTorch 下載站、ModelScope 都通）。
- 環境已建好並在 RTX 3090 上驗證：`torch 2.8.0+cu128`、`torch.cuda.is_available() == True`。
- **最大的意外：SSH 從校外連不上**（必須在校園網或連 CUHK VPN）。這次偵察全程改走 JupyterHub 網頁終端機完成。這會影響設計決定 D4 的「rsync 交換」，見下方「存取方式」與「留給後續 session 的問題」。
- 後續實測：CUHK VPN 在現有設定下**不能**與 Private Internet Access 並存（見「追加測試一」）；IndexTTS-2 與 2.5 都已在 3090 上實際合成成功（見「追加測試二」）。

## 存取方式（實測）

| 途徑 | 校外（家用網路＋Private Internet Access VPN）是否可用 | 備註 |
|---|---|---|
| SSH `scrp-login.econ.cuhk.edu.hk:22`（及 `scrp-login-2`） | **不可**，連線逾時 | 官方說明：須在校園內或連上 CUHK VPN |
| JupyterHub `https://scrp-login.econ.cuhk.edu.hk/jupyter/` | **可**，使用者輸入帳密登入即可 | 內含終端機，可執行 `sbatch`、`compute` 等全部命令 |

```
$ nc -vz -G 6 scrp-login.econ.cuhk.edu.hk 22
nc: connectx to scrp-login.econ.cuhk.edu.hk port 22 (tcp) failed: Operation timed out
$ curl -sL -o /dev/null -w '%{http_code} %{url_effective}\n' https://scrp-login.econ.cuhk.edu.hk/jupyter/
200 https://scrp-login.econ.cuhk.edu.hk/jupyter/hub/login?next=%2Fjupyter%2Fhub%2F
```

- 使用者的 Mac 必須一直開著 Private Internet Access（否則連不上 Claude）。它已設定「137.189.0.0/16（中大網段）不走 VPN」，所以中大網站是直連的，兩者不衝突。
- CUHK VPN 目前是 GlobalProtect 用戶端，官方頁面寫明是分流式（只有校內流量走 VPN）。已安裝並實測：現有設定下與 Private Internet Access **不能並存**，詳見「追加測試一」。
- JupyterHub 的終端機跑在登入節點 `scrp-login` 上，以 systemd 服務限制為 **8 核、10 GB 記憶體**（`CPUQuotaPerSecUSec=8s`、`MemoryMax=10737418240`）。重活一律丟給 `sbatch` / `compute`。
- 已為日後 SSH 做好準備（VPN 通了即可免密碼）：
  - Mac 端：專用金鑰 `~/.ssh/id_ed25519_scrp`；`~/.ssh/config` 新增別名 `scrp`、`scrp2`。
  - 叢集端：公鑰已追加到 `~/.ssh/authorized_keys`（原有的 `root@scrp-control` 那行保留未動）。

## 六個待確認項

### 1. 配額與分區 → 教師級，5 天、最多 4 張 3090

```
$ qos
           User    Account   Def Acct                  QOS   Def QOS
    georgecheng   teachers   teachers       c16-long,c32g8     c32g8

$ sacctmgr -P show qos c32g8,c16-long format=Name,MaxWall,MaxTRESPU
c16-long|30-00:00:00|cpu=16,gres/gpu=1,mem=1600G
c32g8|5-00:00:00|cpu=128,gres/gpu:a100=2,gres/gpu:rtx3090=4,gres/gpu=8,mem=512G,node=4
```

- 預設配額 `c32g8`：單一作業最長 **5 天**；每人合計最多 128 核、512 GB 記憶體、8 張 GPU，其中 **RTX 3090 最多 4 張**、A100 最多 2 張。
- 另有 `c16-long`：最長 30 天，但只有 16 核 1 張 GPU（本專案用不到）。
- 可同時用 1 張以上 GPU：**可以**（要多張時可把一章拆成多個作業並行）。
- RTX 3090 實際共 10 張：`scrp-node-8` 4 張、`scrp-node-9` 4 張（都在預設分區 `scrp`），`scrp-node-22` 2 張（在 `gpu` 分區）。`docs/03` 寫的 `node-10` 實際登記的是另一種顯示卡（Slurm 標籤 `rtxp6000` ×2），且偵察時處於 down 狀態。
- 帳號可用 `gpu` 分區（實測作業被排到 `gpu` 分區執行）。

### 2. 計算節點外網 → 有，且很快

在 `scrp-node-9`（RTX 3090 節點）上以 `compute` 實測：

```
$ compute -c 2 --mem=8G --gpus=rtx3090 -t 10 bash -c '...curl -sI ...'
scrp-node-9
https://huggingface.co -> HTTP/2 200
https://github.com -> HTTP/2 200
https://pypi.org/simple/ -> HTTP/2 200
https://hf-mirror.com -> HTTP/2 200
https://download.pytorch.org/whl/cu128/ -> HTTP/2 200
https://www.modelscope.cn -> HTTP/1.1 302 Found
```

- 無需代理（`http_proxy` / `https_proxy` 為空）。登入節點同樣全通。
- 速度參考：142 個套件（含 torch 與整套 CUDA 執行庫，數 GB）下載只花 3 分 09 秒。
- 結論：**安裝與下載模型權重都直接在 `sbatch` 作業裡做**，不需要在登入節點用 `screen` 迂迴。

### 3. 磁碟配額 → `~/` 50 GB；`~/large-data` 實際可用約 1 TB

```
$ scrp-quota
scrp-control-2:/home      83616K  51200M  56320M        （~/：已用 84 MB / 配額 50 GB）
scrp-archive:/archive         0K   5120G   5500G        （~/archive：5 TB）
   georgecheng|104339||      0 Byte|    1.95 TiB||   0|unlimited   （~/large-data）

$ df -h ~ ~/large-data
scrp-control-2:/home  5.5T  4.9T  318G  95% /home
beegfs_nodev          175T  174T  1.1T 100% /data
```

- `~/large-data` 是指向 `/data/users/georgecheng` 的符號連結（BeeGFS 分散式檔案系統），已確認可寫。
- **配額看起來是雙倍計量**：裝完環境後 `du` 顯示約 17.7 GB，但 `scrp-quota` 顯示已用 35.47 GiB，剛好兩倍。推測是檔案系統做了鏡像、配額按兩份算（未向管理員求證）。若如此，1.95 TiB 的上限等於**實際可放約 1 TB**（與官方文件寫的教師 1000 GB 吻合）。
- **風險**：整個 `/data` 共用池偵察時已用 174T / 175T（顯示 100%），只剩 1.1 TB 給所有人。本專案預計用量（環境 9 GB＋模型權重約 10 GB＋一章音訊數 GB）很小，但若哪天寫入失敗，先查 `df -h ~/large-data`。
- conda 預設把環境放 `~/.conda/envs`、套件快取放 `~/.conda/pkgs`（都在 50 GB 的 `~/`）。已改為 `~/large-data`，`~/.condarc` 現在的內容：

```
envs_dirs:
  - /home/users/georgecheng/large-data/conda/envs
pkgs_dirs:
  - /home/users/georgecheng/large-data/conda/pkgs
```

### 4. GPU 驅動 → 580.65.06，支援到 CUDA 13.0；選用 torch 2.8.0＋cu128

```
$ nvidia-smi        （scrp-node-9）
| NVIDIA-SMI 580.65.06     Driver Version: 580.65.06     CUDA Version: 13.0 |
|   0  NVIDIA GeForce RTX 3090   On | 00000000:C1:00.0 Off |
| 42%   41C   P8   25W / 200W |   1MiB / 24576MiB |   0%   Default |
```

- 每張 3090 有 24 GB 顯示記憶體，功耗上限被設為 200 W（原廠 350 W；推理速度可能略低於網上的 3090 基準，未實測）。
- 驅動向下相容，所以 CUDA 12.x 的 torch 輪子可直接用。IndexTTS 的鎖檔指定 `torch 2.8.x + cu128`（自帶 CUDA 12.8 執行庫），**不需要 `module load cuda`**。
- 登入節點沒有 GPU（`nvidia-smi` 報錯是正常的）。
- 可用模組：`cuda/11.2 … 12.8, 13.0, 13.2(預設)`、`cudnn/8.4.1, 9.10.0, 9.23.0(預設)`。
- 預裝 conda 環境的版本（未使用，僅記錄）：`pytorch` 環境 = Python 3.11.0＋torch 2.12.0+cu132；另有一個 `omnivoice` 環境 = Python 3.13.12＋torch 2.8.0+cu128＋omnivoice 0.1.1（叢集管理員裝的另一個語音合成工具，不在本專案設計內）。

### 5. 長時間佔用 → 允許，餘裕極大

- 單一作業上限 5 天；一章 4400 句預估 1–2 小時，遠低於上限。
- 這次安裝作業的實際耗時：5 分 37 秒（作業 407395，`scrp-node-9`，8 核 12 GB 1 張 3090）。
- **排隊的實際瓶頸是記憶體而不是 GPU**：偵察時 `scrp-node-9` 的 4 張 3090 全空，但有別人的 CPU 作業佔了 480 GB 記憶體，只剩約 15 GB；`scrp-node-8` 的 4 張 3090 全被佔用。要 32 GB 的作業一直排隊，改成 12 GB 並同時指定 `scrp,gpu` 兩個分區後立刻開跑。
  - 對策（已寫進 `setup_env.sh`，S4 的批次腳本請沿用）：`#SBATCH --partition=scrp,gpu`、`--mem` 先要 12–16 GB，真的不夠再加。
  - 注意：`docs/03` 說「RTX 3090 自動配 8 核 48 GB」是 `compute --gpus=rtx3090` 不帶 `-c/--mem` 時的預設；在記憶體吃緊時這個預設會排不上，請明確指定 `--mem`。

### 6. ffmpeg → 沒有預裝（登入節點與計算節點都沒有）

```
$ which ffmpeg
Command 'ffmpeg' not found
```

- 與原設計一致：渲染與編碼在 Mac 做，叢集只寫 WAV（`soundfile` / `torchaudio`）。
- FunASR 在沒有 ffmpeg 時會印一行提示並改用 torchaudio 讀檔，不影響功能：`Notice: ffmpeg is not installed. torchaudio is used to load audio`。
- 後果：叢集端的輸入參考音必須是 WAV（或 torchaudio 不靠 ffmpeg 就能讀的格式）；MP3/OGG 的轉檔請在 Mac 端先做完。真的需要時可用 `conda install -c conda-forge ffmpeg` 裝進 `aktts` 環境（未做）。
- 其他工具：`apptainer 1.5.0`、`git`、`git-lfs`、`screen`、`tmux`、`gcc 11.4.0` 都有。系統：Ubuntu 22.04.5，conda 26.5.2。

## 已建立的環境

由 `cluster/setup_env.sh` 建立（叢集上的副本在 `~/large-data/aktts/setup_env.sh`，SHA-256 與本倉庫一致：`8ad21b03…e9da8`）。

```
~/large-data/
├── conda/
│   ├── envs/aktts/        conda 環境（8.5 GB），Python 3.11.16
│   └── pkgs/              conda 套件快取（0.3 GB）
└── aktts/                 叢集端專案根目錄（環境變數 AKTTS_ROOT）
    ├── env.sh             之後所有作業開頭 `source ~/large-data/aktts/env.sh`
    ├── setup_env.sh       安裝腳本副本
    ├── index-tts/         IndexTTS 原始碼，鎖定提交 d9e41aa（2026-09-29 的 main）
    ├── cache/{pip,uv,hf,modelscope}/   下載快取（8.8 GB，可隨時刪）
    ├── models/            （空）S4 把模型權重放這
    ├── work/              （空）S4 的 manifest、參考音、輸出音訊放這
    └── aktts-setup-407391.log / aktts-setup-407395.log   安裝日誌（前者是失敗的那次）
```

關鍵套件版本：

| 套件 | 版本 |
|---|---|
| torch / torchaudio | 2.8.0+cu128 |
| indextts（可編輯安裝，指向 `index-tts/`） | 2.0.0 |
| funasr | 1.4.16 |
| openai-whisper（IndexTTS 的依賴，順帶可當備用語音辨識） | 20250625 |
| transformers | 4.52.1 |
| numpy | 2.2.6 |
| soundfile / pyyaml | 0.13.1 / 6.0.2 |
| WeTextProcessing / pynini（中文文字正規化） | 1.0.4.1 / 2.1.6 |

驗收輸出（安裝作業 407395 結尾，以及事後另開一個全新作業 407400 用 `env.sh` 再驗一次）：

```
python      3.11.16
torch       2.8.0+cu128 | built for CUDA 12.8
torchaudio  2.8.0+cu128
funasr      1.4.16
soundfile   0.13.1
cuda.is_available: True
device      NVIDIA GeForce RTX 3090
gpu matmul ok: True
SETUP_OK

$ compute -c 2 --mem=8G --gpus=rtx3090 -t 10 bash -c 'source ~/large-data/aktts/env.sh && python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name())"'
scrp-node-9
2.8.0+cu128 True NVIDIA GeForce RTX 3090
```

安裝腳本本身只驗證「能 import、GPU 可用」。實際合成已在稍後的「追加測試二」驗證：IndexTTS-2 與 2.5 都能在這個環境出聲。

## 安裝時踩到的坑（已在腳本中處理）

1. **IndexTTS 釘死 Python 小版本**：倉庫的 `.python-version` 寫 `3.11.13`，`uv sync` 預設會自己下載一份 Python 並拒絕使用 conda 環境（第一次作業 407391 因此失敗）。解法：`uv sync` 加 `--python <conda 環境的 python> --no-managed-python`。
2. **conda 預設頻道**是 `repo.anaconda.com`（可能要求同意條款）；腳本改用 `-c conda-forge --override-channels`，只裝 Python 與 pip，其餘全走 IndexTTS 的 `uv.lock`。
3. **`uv sync` 預設會刪掉鎖檔以外的套件**；加 `--inexact` 保留 pip、uv、funasr。
4. **`UV_LINK_MODE=copy`** 是預防性設定：`~/large-data` 是 BeeGFS，uv 預設用硬連結從快取裝套件，在這類檔案系統上常出問題，所以直接複製（沒有實測過硬連結在此是否可用）。

## 這次偵察對叢集做的改動（全部列出）

| 位置 | 改動 |
|---|---|
| `~/.condarc` | 新建；內容見上方第 3 項 |
| `~/.ssh/authorized_keys` | 追加一行 `ssh-ed25519 … georgecheng@mac-for-scrp` |
| `~/large-data/conda/`、`~/large-data/aktts/` | 新建，內容見上方目錄樹 |
| `~/.local/share/uv/` | 94 MB 殘留：第一次失敗的作業讓 uv 自行下載了一份 Python 3.11.13，沒有任何東西在用它。可安全刪除：`rm -rf ~/.local/share/uv`（本次未刪，留給使用者決定） |

沒有改 `~/.bashrc`，沒有申請任何額外配額，沒有下載任何遊戲資料。偵察階段提交過的作業：407388、407389、407400（各幾秒的探測）、407391（失敗）、407395（成功）。之後應專案擁有者要求做的對比測試另下載了模型權重並提交作業 407406，見「追加測試二」。目前佇列為空。

## 追加測試一：CUHK VPN 與 Private Internet Access 並存（2026-10-02 21:22–21:31）

**結論：在現有設定下不能並存。** 一連上 CUHK VPN，整台 Mac 立刻全面斷網（含 Claude），而且 SSH 仍然不通。

做法：使用者依官方說明安裝 GlobalProtect 6.3.3、入口 `access.cuhk.edu.hk`，在 Private Internet Access 保持連線的情況下連上；Mac 端背景腳本每 5 秒記錄一次，事後對照 GlobalProtect 的服務日誌 `/Library/Logs/PaloAltoNetworks/GlobalProtect/PanGPS.log`。

```
time     | pia       | route_to_scrp | default_route | ssh22  | claude_api
21:24:40 | Connected | en0           | utun4         | closed | DOWN        ← 隧道 21:24:42 建立
21:31:46 | Connected | en0           | utun4         | closed | ok(404)     ← 使用者按 Disconnect 後恢復
```

原因有兩個，都來自兩個 VPN 搶同一段位址與同一個 DNS 設定：

1. **校內流量沒有進隧道，所以 SSH 還是不通。** CUHK VPN 要接管 `137.189.0.0/16`，但 Private Internet Access 的「137.189.0.0/16 不走 VPN」規則已經先佔了同一條路由。日誌原文：`Route 137.189 shadows access route 137.189.0.0/16`；隧道統計 `send packets(68) … recv packets(0)`（送出 68 個封包、一個都沒收到）。
2. **DNS 被換成校內伺服器，於是所有網址都解析不了。** CUHK VPN 把系統 DNS 改成 `137.189.192.3`、`137.189.196.3`（日誌 `tunnel dns is {…}`），而 Private Internet Access 只放行它自己的 DNS（`10.0.0.241`），其他 DNS 查詢一律擋掉（偵察時 `dig @1.1.1.1` 逾時可佐證；這一點是依現象推斷，沒有讀到它的防火牆規則）。

副作用：CUHK VPN 斷線時把那條 `137.189.0.0/16` 路由一併刪了，所以斷線後中大網站改經 Private Internet Access 出去（JupyterHub 實測仍可登入，HTTP 200）；重新連一次 Private Internet Access 就會恢復原狀。

要讓兩者並存，需要同時改 Private Internet Access 的三項設定（關 kill switch、DNS 改用系統既有的、把略過清單從整段 `137.189.0.0/16` 改成只留 VPN 閘道 `137.189.192.215`），這些改動平時也會削弱它的保護，而且每次試錯都會讓 Mac 斷網。**未嘗試**，是否值得由專案擁有者決定。

Mac 端現況：GlobalProtect 已安裝；它的系統擴充功能（Network Extension）沒有啟用，隧道在沒啟用的情況下也能建立。

**GlobalProtect 會自己重連（22:37 再次發生）。** 使用者按 Disconnect 之後它並不會一直保持斷線：22:36:51 偵測到路由變動，日誌出現 `GPC-26003 recovery - 10 consecutive skip-discovery events while disconnected. Forcing network discovery.`，隨即用快取的登入狀態自動連上（22:37:02 `VPN tunnel is connected`），Mac 再次全面斷網，直到使用者 22:40 手動斷開。Claude 先前「不會自動連」的說法是錯的。要避免：在 GlobalProtect 設定視窗按 Sign Out（清掉登入狀態），或用安裝檔的 Uninstall GlobalProtect 選項移除。

## 追加測試二：IndexTTS-2 與 IndexTTS-2.5 試聽對比（作業 407406，`scrp-node-22`，耗時 6 分 21 秒）

腳本：`cluster/ab_indextts.sh`、`cluster/ab_indextts.py`。兩個版本用同 2 段參考音 × 同 4 句自擬的句子各合成一遍，預設參數、未調校。參考音是 IndexTTS 官方示例（各約 2 秒），不是遊戲語音。

| | IndexTTS-2 | IndexTTS-2.5 |
|---|---|---|
| 8 句是否全部合成成功 | 是 | 是 |
| 模型載入時間 | 127.7 秒 | 54.3 秒 |
| 每 1 秒音訊的合成耗時（越小越快） | 1.009 秒 | 0.726 秒 |
| 顯示記憶體峰值 | 8.82 GB | 5.33 GB |
| 權重大小 | 11 GB | 11 GB |

- 以 2.5 版的速度粗估：一章 4400 句若平均每句 5 秒音訊，單張 3090 約 4.4 小時（原估 1–2 小時偏樂觀）；拆成 4 個作業並行可降到 1 小時出頭。這是上限（實際只有幹員台詞走 IndexTTS，NPC、旁白、博士走 ElevenLabs），且只是 8 句的小樣本，僅供量級參考。
- 2.5 版執行時印了一行 `RuntimeError('Ninja is required to load C++ extensions …')`，之後照常完成——某個加速用的 C++ 擴充沒載入、走了較慢的後備路徑。S4 可試 `pip install ninja` 看是否更快。
- 音質與相似度**尚未由人聽審**；哪一版較好由專案擁有者試聽後決定。試聽頁（單一檔案、音訊內嵌）：叢集上 `~/large-data/aktts/work/ab_test/index.html`，登入 JupyterHub 後開 `https://scrp-login.econ.cuhk.edu.hk/jupyter/user/georgecheng/files/large-data/aktts/work/ab_test/index.html`。
- 這個對比只反映通用品質。用遊戲幹員原聲當參考音的效果要等 S3 備好參考音後再驗。
- 叢集新增：`~/large-data/aktts/models/IndexTTS-2/`、`models/IndexTTS-2.5/`（各 11 GB）、`work/ab_test/`、`ab_indextts.sh`、`ab_indextts.py`、`aktts-ab-407406.log`。

> **專案擁有者對追加測試二的評語（2026-10-02）：沒有判斷價值。** 參考音只有 2 秒且是喊叫，所有句子都跟著像喊叫；更根本的是它沒有用原著語音，而專案要回答的問題正是「原著人物的原聲能否被克隆並泛化到原著劇情」。追加測試二的速度與記憶體數字仍可參考，音質結論作廢，以追加測試三為準。

## 追加測試三：用幹員原聲克隆、念 BB-ST-1 真實台詞（作業 407441，`scrp-node-22`，耗時 7 分 38 秒）

腳本：`cluster/real_ab.sh`、`cluster/real_ab.py`。原聲取自 `PseudoMon/arknights-audio` 的 `voice_cn/`（MP3，只下載了本測試用到的 20 個檔到叢集 `work/real_ab/orig/`）。

設計：
- 角色：凯尔希（`char_003_kalts`，主參考音 CN_011「幹員報到」7.8 秒；副參考音 CN_038「新年祝福」12.3 秒）、阿斯卡纶（`char_4132_ascln`，參考音 CN_010「閒置」7.9 秒）。都選語氣平穩的交談語音。
- 同文對比：讓克隆聲線念「原聲裡有、但沒當參考音」的台詞（凯尔希 CN_036、CN_002；阿斯卡纶 CN_001、CN_011），與原聲並排。
- 劇情台詞：BB-ST-1 裡兩人的真實台詞（凯尔希 5 句、阿斯卡纶 4 句）。凯尔希在此場全是喊叫與悲痛的短句，每句做三種：不控情緒／指定情緒向量／用她自己的急促語音 CN_032 當情緒參考（後者只做兩句喊叫）。
- 每個條件只合成一次（固定隨機種子 1234）、預設參數；共 22 條 × 2 個版本，全部合成成功。「Mon3tr」在合成文字裡寫成「Monster」。
- 客觀指標：聲紋相似度（FunASR 的 cam++ 聲紋模型；基準是該角色 6 段未參與的原聲的平均聲紋）、字錯率（FunASR Paraformer 中文辨識回轉文字再比對）。

聲紋相似度（越高越像；刻度：原聲對原聲是上限，換成另一個角色是下限）：

| | 上限 | 下限 | IndexTTS-2 同文 | IndexTTS-2 劇情 | IndexTTS-2.5 同文 | IndexTTS-2.5 劇情 |
|---|---|---|---|---|---|---|
| 凯尔希 | 0.894 | 0.490 | 0.854 | 0.717 | 0.828 | 0.726 |
| 阿斯卡纶 | 0.929 | 0.492 | 0.821 | 0.748 | 0.610 | 0.690 |

觀察到的事實：
1. **平穩語句的音色相似度接近上限。** 凯尔希同文對比 0.83–0.87，上限 0.894。
2. **指定情緒向量會讓音色跑掉。** 凯尔希劇情台詞「不控情緒」0.67–0.84，加情緒向量後降到 0.52–0.75（兩個版本每一句都降，降幅 0.06–0.18）。用她自己的語音當情緒參考時降得較少（0.72–0.77）。情緒本身像不像無法用數字判斷，需人聽。
3. **IndexTTS-2.5 在阿斯卡纶的兩句長台詞上失敗。** 原聲 8.9 秒與 11.5 秒的句子，2.5 版輸出了 32.1 秒與 50.5 秒的音訊，辨識結果只有前半句（後半句內容丟失），相似度也掉到 0.59 與 0.63。IndexTTS-2 同樣兩句正常（9.7 秒、10.8 秒，內容完整）。凯尔希的長句（63 字）兩版都正常。只試了一次，尚不知是偶發還是穩定重現。
4. **短促喊叫容易咬字錯。** 「阿米娅！博士！」的「博士」在兩個版本、多種做法下都被辨識成「不是」「不湿」之類；情緒向量版偶爾多出語氣詞（「啊 Monster 切开门」）或錯字（「解开门」）。
5. **字錯率被專有名詞同音字灌水。** 「特蕾西娅」辨識成「特雷西亚」、「阿斯卡纶」成「阿斯卡伦」、「凯尔希」成「凯尔西」、「征象」成「征相」，發音其實是對的。設計決定 D12 的回檢要先做同音歸一（例如轉成拼音再比），否則這類句子會全部被誤判為失敗。
6. 速度與上次一致：IndexTTS-2 每秒音訊 1.074 秒、顯示記憶體峰值 10.08 GB；IndexTTS-2.5 為 0.715 秒、6.70 GB。

限制：每個條件只有一次取樣、兩個角色、情緒向量是我憑台詞語境手填的；聲紋相似度只衡量音色，不衡量語氣和演技。**最終判斷要靠專案擁有者試聽。**

試聽頁（單一檔案 7.9 MB，音訊內嵌，含原聲、兩個版本、每條的相似度與辨識結果）：叢集上 `~/large-data/aktts/work/real_ab/report.html`，登入 JupyterHub 後開 `https://scrp-login.econ.cuhk.edu.hk/jupyter/user/georgecheng/files/large-data/aktts/work/real_ab/report.html`。逐條數據在同目錄 `results.json`。

**未做：ElevenLabs 克隆基準。** 專案擁有者提出把角色語音放進 ElevenLabs 克隆、以其最新模型當基準。Claude 未執行：建立克隆聲線須聲明已取得聲音主人同意，而素材是聲優錄音；這也與設計決定 D3 及風險表「不上傳任何聲優音訊到 ElevenLabs」一致。若專案擁有者自行用其帳號產生樣本，可放進專案後併入同一張對比表。

> **專案擁有者對追加測試三的評語（2026-10-02）：不微調聽起來很差；而且 IndexTTS 只用一段參考音，浪費了每個角色的整池語音。** 查原始碼屬實：`spk_audio_prompt` 只收一個檔，超過 15 秒截斷（`_load_and_cut_audio(spk_audio_prompt, 15, …)`），官方說明沒有任何微調或訓練的做法。因此追加測試四改試可微調的 GPT-SoVITS。

## 追加測試四：用凯尔希整池原聲微調 GPT-SoVITS（2026-10-02 至 10-03，最終作業 408881）

腳本：`cluster/gsv_finetune.sh`（安裝→資料→訓練→合成→試聽頁，可重複執行）、`cluster/gsv_pipeline.py`、`cluster/gsv_report.py`。GPT-SoVITS 鎖定提交 `48b1a016`（2026-08-18），模型版本 v2Pro，參數全用官方介面預設值（SoVITS 8 輪、GPT 15 輪，批次 12）。

- 訓練資料：凯尔希 38 句中文原聲中的 36 句、共 4.51 分鐘；「同一句話」對比用的 CN_002、CN_036 不進訓練。每句的原文取自語音表 `charword_table.json`，不需聽寫。
- 訓練耗時：SoVITS 192 秒＋GPT 55 秒，單張 RTX 3090 約 4 分鐘一個角色。合成很快，11.5 秒的音訊約 2.5 秒生成（IndexTTS-2 約是 1 秒音訊耗 1 秒）。
- 合成內容與追加測試三相同（2 句同文＋5 句 BB-ST-1 台詞），共 19 條全部成功：未微調底模 7 條、微調後 12 條。微調後的劇情台詞各做兩種參考音：平穩的 CN_011，與「語氣相近」的參考音（急促用 CN_031「评估一下逃亡人员的危险系数…」，低沉用 CN_013「越是强大越是脆弱…」）。後兩句是依台詞內容挑的，**沒有人聽過確認語氣是否真的相近**；另外每次合成都附 5 句原聲當輔助參考音。

聲紋相似度（凯尔希；上限 0.894、下限 0.490，定義同追加測試三）：

| | 同一句話（2 句平均） | 劇情台詞（5 句平均） |
|---|---|---|
| IndexTTS-2，單一參考音、不控情緒（追加測試三） | 0.840 | 0.784 |
| GPT-SoVITS 未微調 | 0.788 | 0.753 |
| GPT-SoVITS 微調後，平穩參考音 | 0.844 | 0.794 |
| GPT-SoVITS 微調後，語氣相近參考音 | — | 0.796 |

觀察到的事實：
1. **微調確實讓 GPT-SoVITS 更像**：同文 0.788 → 0.844，劇情 0.753 → 0.794。
2. **但以聲紋相似度衡量，微調後的 GPT-SoVITS 與不微調的 IndexTTS-2 基本打平**（0.844 對 0.840；0.794 對 0.784），差距小於單次取樣的波動。這個指標只量音色，量不到語氣與演技，所以「聽起來好不好」仍要專案擁有者試聽判斷。
3. **GPT-SoVITS 念英文詞更差**：「Monster，切开门！」三種做法辨識成「貌似卸开门」「孟子切开门」「孟随即开门」，IndexTTS-2 念對了。「阿米娅！博士！」的「博士」仍被辨識成「不是」，與 IndexTTS 相同。微調後的長句另有一處錯字（「权限」→「缺陷」）。
4. 換成「語氣相近」的參考音，相似度沒有明顯變化；語氣是否更對需人聽。
5. 值得注意的資料限制：幹員語音池幾乎都是平穩的交談與簡短指令，**沒有 BB-ST-1 那種喊叫與悲痛的樣本**，所以不論用哪個引擎、微調與否，激烈情緒都得靠模型自己推，池子裡沒有可學的示範。

試聽頁（單一檔案 4.1 MB，含原聲、IndexTTS-2、未微調、微調後兩種參考音）：叢集上 `~/large-data/aktts/work/gsv_kalts/report.html`，登入 JupyterHub 後開 `https://scrp-login.econ.cuhk.edu.hk/jupyter/user/georgecheng/files/large-data/aktts/work/gsv_kalts/report.html`。逐條數據在同目錄 `results.json`。

限制：只做了凯尔希一個角色、每個條件一次取樣、官方預設輪數未調。

叢集新增：conda 環境 `~/large-data/conda/envs/aktts-gsv`（Python 3.10、torch 2.11.0+cu128，約 9 GB）、`~/large-data/aktts/GPT-SoVITS/`（含預訓練模型與訓練出的權重，8.6 GB）、`work/gsv_kalts/`（38 句原聲、訓練標註、輸出）。`~/large-data/aktts/env.sh` 的 conda 路徑改成寫死 `/opt/network/anaconda3`（經 SSH 提交的作業環境裡沒有 conda 命令）。

安裝與執行時踩到的坑（都已寫進腳本）：
1. 官方 `install.sh` 是子行程，要先把 conda 的 `condabin` 放進 PATH，否則報 `Conda Not Found`。
2. `pip install -r requirements.txt` 的依賴解析會反覆回溯，20 分鐘未完成；改讓 `install.sh` 用 uv 後 3 分鐘裝完。
3. `torchaudio` 會從 PyPI 裝到 CUDA 13 的版本，與 cu128 的 torch 衝突，需重裝同版本的 cu128 版。
4. `torchcodec`（torchaudio 讀音檔用）要同時滿足三件事才載得起來：FFmpeg ≤ 8（`install.sh` 會裝到 9）、conda 環境的 `lib` 在 `LD_LIBRARY_PATH` 上、用 CPU 版（cu128 版需要叢集上沒有的 `libnppicc.so.12`）。
5. 官方特徵抽取腳本逐檔吞掉例外：第 4 點沒修好時聲紋特徵是空的，流程卻照常往下訓練。腳本現在會數檔案，不齊就停。
6. `SoVITS_weights_v2Pro/`、`GPT_weights_v2Pro/` 要先建好，否則訓練跑完但權重存不下來。
7. 切換權重的函式不帶語言參數會在最後丟 `UnboundLocalError`；自建的翻譯物件要與它用同一語言（環境變數 `language=zh_CN`），否則報 `KeyError('Chinese')`。
8. 參考音必須在 3–10 秒之間，否則直接報錯。

## 留給後續 session 的問題

1. **檔案交換方式（影響設計決定 D4 與 S4 的 `pipeline cluster push/pull`）**：原設計假設 Mac 能直接 rsync 到叢集，但校外 SSH 不通，CUHK VPN 在現有設定下又無法與 Private Internet Access 並存（見追加測試一）。剩下的路，需專案擁有者決定（屬於「叢集權限」邊界問題）：
   - 不靠 SSH，走 JupyterHub 的 HTTPS 介面。S0 全程就是這樣做的：傳檔、提交作業、讀結果都已驗證可行。目前靠使用者在瀏覽器登入後由 Claude 操作；若要讓 Mac 端的 `pipeline cluster push/pull` 全自動，需要使用者在 JupyterHub 產生一個存取權杖放進本機設定檔（未做、未驗證 SCRP 是否開放權杖功能）。
   - 人在校園網時用 SSH（金鑰與別名 `scrp` 已備好，未實測）。
   - 修改 Private Internet Access 的三項設定以求並存（見追加測試一，未嘗試）。
   - **更新（2026-10-02 23:31）**：GlobalProtect 自動重連的那次，SSH 金鑰登入實測成功。原因是它前一次斷線時刪掉了 Private Internet Access 的 `137.189.0.0/16` 路由，校內流量因此進了隧道；剩下的唯一障礙是系統 DNS 被換成校內伺服器而查詢出不去。專案擁有者決定另開 session 把並存修好，任務書在 `docs/sessions/S0b-vpn-coexistence.md`。
2. **引擎與做法（設計決定 D3）**：專案擁有者試聽後認為不微調的 IndexTTS 效果差。追加測試四顯示微調 GPT-SoVITS 在聲紋相似度上與 IndexTTS-2 打平，音質與語氣待他試聽；兩套環境都已在叢集上可用。以下是原先關於 IndexTTS 兩個版本的記錄。兩版都已裝好、都能合成。2.5 版較快較省記憶體，但在追加測試三中有兩句長台詞輸出失控、音色相似度也略低；IndexTTS-2 全部正常。最終由專案擁有者試聽追加測試三的試聽頁後決定。
   - 連帶待解：情緒怎麼給（情緒向量會讓音色跑掉；用角色自己的語音當情緒參考較穩）、短促喊叫的咬字、回檢的同音字歸一。設計決定 D13「第一版不控情緒」在巴別塔這種情緒激烈的場景是否成立，需專案擁有者聽過「不控情緒」那一欄後判斷。
3. **加速選項未裝**：`uv sync` 沒帶 `--extra accel`（flash-attn）與 `--extra deepspeed`；2.5 版另缺 `ninja`。
4. **3090 節點記憶體吃緊**：批次腳本的 `--mem` 請保守（見第 5 項）。這次對比作業要 24 GB，被排到 `gpu` 分區的 `scrp-node-22` 才立刻開跑。
