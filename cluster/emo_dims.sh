#!/usr/bin/env bash
# 情緒維度拆解（凯尔希，IndexTTS-2）。用法： cd ~/large-data/aktts && sbatch emo_dims.sh
#SBATCH --job-name=aktts-emodims
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=4
#SBATCH --mem=20G
#SBATCH --time=0-00:30
#SBATCH --output=%x-%j.log
set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
cd "$AKTTS_ROOT/index-tts"
python "$AKTTS_ROOT/emo_dims.py" gen
python "$AKTTS_ROOT/emo_dims.py" report
