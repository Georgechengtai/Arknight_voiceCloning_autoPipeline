#!/usr/bin/env bash
# 混合方案試驗（凯尔希）：IndexTTS 的節奏 ＋ 微調後 SoVITS 的聲音。
# 前置：real_ab.sh、gsv_finetune.sh、ref_catalog.sh、round2.sh 都已跑過。
# 用法： cd ~/large-data/aktts && sbatch hybrid.sh
#SBATCH --job-name=aktts-hybrid
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=0-00:30
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
AKTTS_ENV="$CONDA_PREFIX"
GSV_ENV="$HOME/large-data/conda/envs/aktts-gsv"
P="$AKTTS_ROOT/hybrid.py"

set +u; conda activate "$GSV_ENV"; set -u
( cd "$AKTTS_ROOT/GPT-SoVITS"
  export PYTHONPATH="$PWD:$PWD/GPT_SoVITS" LD_LIBRARY_PATH="$GSV_ENV/lib:${LD_LIBRARY_PATH:-}"
  export language=zh_CN is_half=True version=v2Pro
  python "$P" convert )
set +u; conda activate "$AKTTS_ENV"; set -u
python "$P" report
ls -la "$AKTTS_ROOT/work/hybrid_kalts" | tail -5
