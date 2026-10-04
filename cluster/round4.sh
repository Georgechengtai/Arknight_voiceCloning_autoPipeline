#!/usr/bin/env bash
# 第四輪（凯尔希長句）：參考音逐句挑、情緒輕量疊加；IndexTTS-2 與 2.5 同條件。
# 前置：round3.sh 已跑過。用法： cd ~/large-data/aktts && sbatch round4.sh
#SBATCH --job-name=aktts-round4
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=0-01:00
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
P="$AKTTS_ROOT/round4.py"
for ver in v2 v25; do
  printf '\n[round4 %s] IndexTTS %s\n' "$(date +%H:%M:%S)" "$ver"
  ( cd "$AKTTS_ROOT/index-tts" && python "$P" idx "$ver" ) || echo "IDX_FAILED $ver"
done
printf '\n[round4 %s] 試聽頁\n' "$(date +%H:%M:%S)"
python "$P" report || echo "REPORT_FAILED"
