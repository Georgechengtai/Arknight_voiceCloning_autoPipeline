#!/usr/bin/env bash
# GPT-SoVITS 少量樣本微調試驗（凯尔希）：安裝 → 資料 → 訓練 → 合成 → 試聽頁。
# 用法： cd ~/large-data/aktts && sbatch gsv_finetune.sh        可重複執行，已完成的階段會跳過。
#SBATCH --job-name=aktts-gsv
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=8
#SBATCH --mem=28G
#SBATCH --time=0-03:00
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u     # 快取位置＋ aktts 環境（報表階段用）
AKTTS_ENV="$CONDA_PREFIX"
GSV_ENV="$HOME/large-data/conda/envs/aktts-gsv"
REPO="$AKTTS_ROOT/GPT-SoVITS"
GSV_REF="48b1a0169a28582a8984402f82cf438d3bfa6aca"         # 2026-08-18 的 main
WORK="$AKTTS_ROOT/work/gsv_kalts"
log() { printf '\n[gsv %s] %s\n' "$(date +%H:%M:%S)" "$*"; }
# 只用 conda-forge，避開預設頻道的條款確認
export CONDA_CHANNELS=conda-forge CONDA_DEFAULT_CHANNELS=https://conda.anaconda.org/conda-forge CONDA_PLUGINS_AUTO_ACCEPT_TOS=yes
export language=zh_CN is_half=True version=v2Pro

log "節點 $(hostname)；$(nvidia-smi --query-gpu=name --format=csv,noheader)"
if [ ! -x "$GSV_ENV/bin/python" ]; then
  log "建立 conda 環境 aktts-gsv（Python 3.10）"
  conda create -y -q -p "$GSV_ENV" -c conda-forge --override-channels python=3.10 pip
fi
if [ ! -d "$REPO/.git" ]; then
  log "clone GPT-SoVITS"
  git clone -q https://github.com/RVC-Boss/GPT-SoVITS.git "$REPO"
  git -C "$REPO" checkout -q "$GSV_REF"
fi
set +u; conda activate "$GSV_ENV"; set -u
cd "$REPO"
export PYTHONPATH="$REPO:$REPO/GPT_SoVITS"
export PATH="$(conda info --base)/condabin:$PATH"   # install.sh 是子行程，需要在路徑上找得到 conda
if [ ! -f .aktts_installed ]; then
  log "官方 install.sh（torch cu128、依賴、預訓練模型；首次約 10–20 分鐘）"
  # pip 的依賴解析在這份 requirements.txt 上會反覆回溯（實測 20 分鐘仍未完成），改讓 install.sh 用 uv 安裝
  python -m pip install -q uv
  export UV_PYTHON="$GSV_ENV/bin/python"
  sed -i 's/output=$(pip install "$@" 2>&1)/output=$(uv pip install "$@" 2>\&1)/' install.sh
  grep -q 'uv pip install' install.sh
  bash install.sh --device CU128 --source HF 2>&1 | tr '\r' '\n' | grep -v -E '^\s*$|%\[|\.\.\.\.\.| [0-9]+[KM] ' || true
  python -c "import torch; assert torch.cuda.is_available(); print('torch', torch.__version__, torch.cuda.get_device_name(0))"
  test -f GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth && test -f GPT_SoVITS/pretrained_models/s1v3.ckpt
  touch .aktts_installed
fi

# requirements.txt 裡的 torchaudio 會從 PyPI 裝到 CUDA 13 的版本，與 cu128 的 torch 不相容（實測報錯）；換成同版同 CUDA
TV=$(python -c 'import torch; print(torch.__version__)')
AV=$(python -c 'import importlib.metadata as m; print(m.version("torchaudio"))')
if [ "$AV" != "$TV" ]; then
  log "torchaudio $AV 與 torch $TV 不匹配，重裝"
  UV_PYTHON="$GSV_ENV/bin/python" uv pip install --reinstall-package torchaudio "torchaudio==$TV" \
    --index-url https://download.pytorch.org/whl/cu128
  python -c 'import torch, torchaudio; print("torchaudio", torchaudio.__version__, "ok with torch", torch.__version__)'
fi

# torchaudio 靠 torchcodec 讀音檔，實測要三件事同時成立才載得起來：
#   1) FFmpeg 的動態庫在載入路徑上（conda 環境的 lib 目錄預設不在）；
#   2) FFmpeg 版本 ≤ 8（install.sh 會裝到 9，torchcodec 0.11 不支援）；
#   3) 用 CPU 版 torchcodec（cu128 版需要 NVIDIA 的 libnppicc.so.12，叢集上沒有）。
# 官方的特徵抽取腳本會逐檔吞掉這個錯誤照常結束，所以務必在這裡先驗。
export LD_LIBRARY_PATH="$GSV_ENV/lib:${LD_LIBRARY_PATH:-}"
if ! python -c "import torchcodec" 2>/dev/null; then
  log "torchcodec 無法載入：改裝 FFmpeg 8 與 CPU 版 torchcodec"
  conda install -y -q -p "$GSV_ENV" -c conda-forge --override-channels "ffmpeg>=8,<9"
  CV=$(python -c 'import importlib.metadata as m; print(m.version("torchcodec").split("+")[0])')
  UV_PYTHON="$GSV_ENV/bin/python" uv pip install --reinstall-package torchcodec "torchcodec==$CV" --index-url https://pypi.org/simple
fi
python -c 'import torchcodec; print("torchcodec", torchcodec.__version__, "ok")'

P="$AKTTS_ROOT/gsv_pipeline.py"
stage() {  # stage <名稱> <完成標記檔>
  if [ -f "$2" ]; then log "$1：已完成，跳過"; else log "$1"; python "$P" "$1"; touch "$2"; fi
}
mkdir -p "$WORK"
stage data     "$WORK/.done_data"
stage prepare  "$WORK/.done_prepare"
stage train_s2 "$WORK/.done_s2"
stage train_s1 "$WORK/.done_s1"
log "infer"; python "$P" infer

log "試聽頁（切回 aktts 環境算相似度與字錯率）"
set +u; conda activate "$AKTTS_ENV"; set -u
unset PYTHONPATH
python "$AKTTS_ROOT/gsv_report.py" || echo "GSV_REPORT_FAILED"
log "完成"; ls -la "$WORK" "$WORK/gen"
