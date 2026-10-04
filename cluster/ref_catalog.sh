#!/usr/bin/env bash
# 參考音目錄：逐句分析一位幹員的全部中文原聲。
# 用法： cd ~/large-data/aktts && sbatch ref_catalog.sh [短名 charId 顯示名]     預設凯尔希
#SBATCH --job-name=aktts-refcat
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=0-00:30
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
python "$AKTTS_ROOT/ref_catalog.py" "${1:-kalts}" "${2:-char_003_kalts}" "${3:-凯尔希}"
ls -la "$AKTTS_ROOT/work/refs/${1:-kalts}"
