#!/usr/bin/env bash
# 第二輪劇情台詞合成（凯尔希）：切片與挑參考音 → GPT-SoVITS → IndexTTS-2 → 試聽頁。
# 前置：已跑過 ref_catalog.sh（原聲與 catalog.json）與 gsv_finetune.sh（微調權重）。
# 用法： cd ~/large-data/aktts && sbatch round2.sh
#SBATCH --job-name=aktts-round2
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=0-01:00
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
AKTTS_ENV="$CONDA_PREFIX"
GSV_ENV="$HOME/large-data/conda/envs/aktts-gsv"
P="$AKTTS_ROOT/round2.py"
log() { printf '\n[round2 %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

log "切片、拼接、量測、挑參考音"
python "$P" segments

log "GPT-SoVITS（微調後）"
set +u; conda activate "$GSV_ENV"; set -u
( cd "$AKTTS_ROOT/GPT-SoVITS"
  export PYTHONPATH="$PWD:$PWD/GPT_SoVITS" LD_LIBRARY_PATH="$GSV_ENV/lib:${LD_LIBRARY_PATH:-}"
  export language=zh_CN is_half=True version=v2Pro
  python "$P" gsv ) || echo "GSV_FAILED"

log "IndexTTS-2"
set +u; conda activate "$AKTTS_ENV"; set -u
( cd "$AKTTS_ROOT/index-tts" && python "$P" idx ) || echo "IDX_FAILED"

log "試聽頁"
python "$P" report || echo "REPORT_FAILED"
log "完成"; ls -la "$AKTTS_ROOT/work/round2_kalts"
