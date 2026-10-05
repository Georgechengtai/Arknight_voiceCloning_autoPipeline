#!/usr/bin/env bash
# 整場合成的對照實驗（IndexTTS-2）。用法： cd ~/large-data/aktts && sbatch scene_variants.sh <job.json>
#SBATCH --job-name=aktts-scvar
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=0-02:00
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
JOB=$(realpath "$1")
( cd "$AKTTS_ROOT/index-tts" && python "$AKTTS_ROOT/scene_variants.py" "$JOB" ) || echo "SCENE_VARIANTS_FAILED"
