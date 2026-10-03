#!/usr/bin/env bash
# SCRP 端 TTS 環境安裝腳本（S0 初稿）。
#
# 做什麼：在 ~/large-data 下建立 conda 環境 aktts（Python 3.11 + torch 2.8 cu128
# + IndexTTS + FunASR），最後驗證 import 成功且 torch.cuda.is_available() 為 True。
# 不做什麼：不下載模型權重、不下載任何遊戲資料、不跑 TTS（那是 S4 的事）。
#
# 用法（在 SCRP 登入節點或 JupyterHub 終端機；計算節點有外網，所以整個安裝在計算節點跑）：
#   背景： sbatch setup_env.sh                  # 日誌寫到提交目錄的 aktts-setup-<jobid>.log
#   前台： compute -c 8 --mem=12G --gpus=rtx3090 -t 2:00:00 bash setup_env.sh
# 可重複執行（已完成的步驟會跳過）。事實依據見 cluster/ENV.md。
#
# 記憶體只要 12G：3090 節點的記憶體常被別人的 CPU 作業佔滿（S0 實測 node-9 只剩 15 GB），
# 要太多會一直排隊。分區同時給 scrp 與 gpu，哪邊有空的 3090 就去哪邊。
#SBATCH --job-name=aktts-setup
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=8
#SBATCH --mem=12G
#SBATCH --time=0-02:00
#SBATCH --output=%x-%j.log

set -euo pipefail

# ---- 可調參數 ---------------------------------------------------------------
AKTTS_ROOT="${AKTTS_ROOT:-$HOME/large-data/aktts}"          # 叢集端專案根目錄（無備份的高速盤）
CONDA_DATA="${CONDA_DATA:-$HOME/large-data/conda}"          # conda 環境與套件快取
ENV_PREFIX="$CONDA_DATA/envs/aktts"
PY_VER="3.11"                                               # index-tts 要求 >=3.10,<3.12
INDEXTTS_REPO="https://github.com/index-tts/index-tts.git"
INDEXTTS_REF="${INDEXTTS_REF:-d9e41aac89fd00b3d71497fddb287b7f24613712}"  # 2026-09-29 的 main，鎖定以便重現
# 設為 1 可在沒有 GPU 的節點上只驗證 import（預設要求 GPU 可用）
AKTTS_SKIP_GPU_CHECK="${AKTTS_SKIP_GPU_CHECK:-0}"

log() { printf '\n[setup_env %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

log "節點 $(hostname)；GPU：$(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null || echo 無)"

# ---- 1. 目錄與快取位置（全部放 ~/large-data，不佔 ~/ 的配額）------------------
mkdir -p "$AKTTS_ROOT"/{cache/pip,cache/uv,cache/hf,cache/modelscope,models,work} \
         "$CONDA_DATA"/{envs,pkgs}
export PIP_CACHE_DIR="$AKTTS_ROOT/cache/pip"
export PIP_DISABLE_PIP_VERSION_CHECK=1
export UV_CACHE_DIR="$AKTTS_ROOT/cache/uv"
export UV_LINK_MODE=copy            # ~/large-data 是 BeeGFS，硬連結不可靠，直接複製
export HF_HOME="$AKTTS_ROOT/cache/hf"
export MODELSCOPE_CACHE="$AKTTS_ROOT/cache/modelscope"

# ---- 2. conda：環境與套件快取指向 ~/large-data（寫入 ~/.condarc）--------------
# shellcheck disable=SC1091
set +u; source "$(conda info --base)/etc/profile.d/conda.sh"; set -u
if ! conda config --show envs_dirs | grep -qF "$CONDA_DATA/envs"; then
  conda config --add envs_dirs "$CONDA_DATA/envs"
fi
if ! conda config --show pkgs_dirs | grep -qF "$CONDA_DATA/pkgs"; then
  conda config --add pkgs_dirs "$CONDA_DATA/pkgs"
fi

# ---- 3. 建環境（只裝 Python 與 pip；其餘全走 pip/uv 以對齊 index-tts 的鎖檔）--
if [ ! -x "$ENV_PREFIX/bin/python" ]; then
  log "建立 conda 環境 $ENV_PREFIX（Python $PY_VER）"
  conda create -y -q -p "$ENV_PREFIX" -c conda-forge --override-channels "python=$PY_VER" pip
else
  log "conda 環境已存在，跳過建立"
fi
set +u; conda activate "$ENV_PREFIX"; set -u
python -m pip install -q -U pip uv

# ---- 4. 取得 index-tts 原始碼（不拉 LFS 範例音檔）-----------------------------
if [ ! -d "$AKTTS_ROOT/index-tts/.git" ]; then
  log "clone index-tts"
  GIT_LFS_SKIP_SMUDGE=1 git clone "$INDEXTTS_REPO" "$AKTTS_ROOT/index-tts"
fi
cd "$AKTTS_ROOT/index-tts"
if [ "$(git rev-parse HEAD)" != "$INDEXTTS_REF" ]; then
  GIT_LFS_SKIP_SMUDGE=1 git fetch -q origin
  GIT_LFS_SKIP_SMUDGE=1 git checkout -q "$INDEXTTS_REF"
fi
log "index-tts @ $(git rev-parse --short HEAD)"

# ---- 5. 依 index-tts 的 uv.lock 安裝依賴到 conda 環境 -------------------------
# uv.lock 把 torch/torchaudio 鎖在 2.8.x + cu128（自帶 CUDA 12.8 執行庫；
# 叢集驅動 580.65.06 支援到 CUDA 13.0，向下相容）。
# --inexact：不要刪掉環境裡鎖檔以外的套件（pip、uv、之後的 funasr）。
# --python + --no-managed-python：index-tts 的 .python-version 釘死 3.11.13，不指定的話
#   uv 會自己下載一份 Python 並拒絕使用 conda 環境（S0 實測踩到）。
# 不裝 extras（webui / deepspeed / accel）；S4 若要加速再評估。
log "uv sync（torch 等大檔案第一次約需數分鐘）"
UV_PROJECT_ENVIRONMENT="$ENV_PREFIX" uv sync --frozen --inexact --no-dev \
  --python "$ENV_PREFIX/bin/python" --no-managed-python

# ---- 6. 質檢與工具套件 --------------------------------------------------------
log "安裝 funasr / soundfile / pyyaml"
uv pip install --python "$ENV_PREFIX/bin/python" funasr soundfile pyyaml

# ---- 7. 產生 env.sh：之後的批次作業只要 source 這個檔 --------------------------
cat > "$AKTTS_ROOT/env.sh" <<EOF
# 由 cluster/setup_env.sh 產生。用法： source ~/large-data/aktts/env.sh
export AKTTS_ROOT="$AKTTS_ROOT"
export PIP_CACHE_DIR="\$AKTTS_ROOT/cache/pip"
export UV_CACHE_DIR="\$AKTTS_ROOT/cache/uv"
export UV_LINK_MODE=copy
export HF_HOME="\$AKTTS_ROOT/cache/hf"
export MODELSCOPE_CACHE="\$AKTTS_ROOT/cache/modelscope"
source "$(conda info --base)/etc/profile.d/conda.sh"   # 產生時就寫成固定路徑：經 SSH 提交的作業環境裡沒有 conda 命令
conda activate "$ENV_PREFIX"
EOF

# ---- 8. 驗證 ------------------------------------------------------------------
log "驗證 import 與 GPU"
AKTTS_SKIP_GPU_CHECK="$AKTTS_SKIP_GPU_CHECK" python - <<'PY'
import os, sys
import torch, torchaudio, soundfile, yaml
import funasr
from indextts.infer_v2 import IndexTTS2  # noqa: F401  只驗證能 import，不載入權重

print("python     ", sys.version.split()[0])
print("torch      ", torch.__version__, "| built for CUDA", torch.version.cuda)
print("torchaudio ", torchaudio.__version__)
print("funasr     ", funasr.__version__)
print("soundfile  ", soundfile.__version__)
ok = torch.cuda.is_available()
print("cuda.is_available:", ok)
if ok:
    print("device     ", torch.cuda.get_device_name(0))
    x = torch.randn(1024, 1024, device="cuda")
    print("gpu matmul ok:", bool(torch.isfinite((x @ x).sum()).item()))
elif os.environ.get("AKTTS_SKIP_GPU_CHECK") != "1":
    sys.exit("FAIL: torch.cuda.is_available() 為 False（請在 GPU 節點上執行，或設 AKTTS_SKIP_GPU_CHECK=1）")
print("SETUP_OK")
PY

log "完成。環境：$ENV_PREFIX ；之後使用： source $AKTTS_ROOT/env.sh"
