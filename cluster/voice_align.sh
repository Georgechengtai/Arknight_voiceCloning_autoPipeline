#!/usr/bin/env bash
# 回聽對齊（只做語音辨識）。用法： cd ~/large-data/aktts && sbatch voice_align.sh <job.json>
#SBATCH --job-name=aktts-valign
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=0-01:00
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
JOB=$(realpath "$1")
python "$AKTTS_ROOT/voice_align.py" "$JOB" || echo "VOICE_ALIGN_FAILED"
