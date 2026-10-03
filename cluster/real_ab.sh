#!/usr/bin/env bash
# 下載兩位幹員的中文原聲，用 IndexTTS-2 與 2.5 各克隆一遍並產生試聽頁。
# 用法： cd ~/large-data/aktts && sbatch real_ab.sh
#SBATCH --job-name=aktts-realab
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=0-01:00
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
WORK="$AKTTS_ROOT/work/real_ab"
SRC="https://raw.githubusercontent.com/PseudoMon/arknights-audio/master/voice_cn"
log() { printf '\n[realab %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

log "下載原聲（只取本測試用到的語音）"
fetch() {  # fetch <短名> <charId> <語音編號...>
  local key="$1" cid="$2"; shift 2
  mkdir -p "$WORK/orig/$key"
  for v in "$@"; do
    [ -s "$WORK/orig/$key/$v.mp3" ] || curl -fsSL -m 60 "$SRC/$cid/$v.mp3" -o "$WORK/orig/$key/$v.mp3"
  done
}
fetch kalts char_003_kalts  CN_002 CN_003 CN_005 CN_006 CN_007 CN_008 CN_009 CN_011 CN_032 CN_036 CN_038
fetch ascln char_4132_ascln CN_001 CN_002 CN_003 CN_004 CN_005 CN_006 CN_007 CN_010 CN_011
ls "$WORK"/orig/*

cd "$AKTTS_ROOT/index-tts"
for ver in v2 v25; do
  log "合成：$ver"
  python "$AKTTS_ROOT/real_ab.py" gen "$ver" || echo "GEN_FAILED $ver"
done
log "相似度、字錯率與試聽頁"
python "$AKTTS_ROOT/real_ab.py" report || echo "REPORT_FAILED"
log "完成"; ls -la "$WORK"
