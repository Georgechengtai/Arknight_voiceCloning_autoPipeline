#!/usr/bin/env bash
# 第三輪（凯尔希平穩長句）：IndexTTS-2 → IndexTTS-2.5 → GPT-SoVITS 與混合 → 試聽頁。
# 前置：round2.sh 已跑過（refs.json）、gsv_finetune.sh 已跑過（微調權重）。
# 用法： cd ~/large-data/aktts && sbatch round3.sh
#SBATCH --job-name=aktts-round3
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=0-01:30
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
AKTTS_ENV="$CONDA_PREFIX"
GSV_ENV="$HOME/large-data/conda/envs/aktts-gsv"
P="$AKTTS_ROOT/round3.py"
log() { printf '\n[round3 %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

for ver in v2 v25; do
  log "IndexTTS $ver"
  ( cd "$AKTTS_ROOT/index-tts" && python "$P" idx "$ver" ) || echo "IDX_FAILED $ver"
done

log "GPT-SoVITS 與混合方案"
set +u; conda activate "$GSV_ENV"; set -u
( cd "$AKTTS_ROOT/GPT-SoVITS"
  export PYTHONPATH="$PWD:$PWD/GPT_SoVITS" LD_LIBRARY_PATH="$GSV_ENV/lib:${LD_LIBRARY_PATH:-}"
  export language=zh_CN is_half=True version=v2Pro
  python "$P" gsv ) || echo "GSV_FAILED"

log "試聽頁"
set +u; conda activate "$AKTTS_ENV"; set -u
python "$P" report || echo "REPORT_FAILED"
log "完成"
