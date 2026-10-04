#!/usr/bin/env bash
# 參考音目錄：下載一位幹員的全部中文原聲，逐句量測、切片、拼接，產生可選的參考音清單。
# 用法： cd ~/large-data/aktts && sbatch ref_catalog.sh                      ref_chars.tsv 裡的全部角色
#        cd ~/large-data/aktts && sbatch ref_catalog.sh <短名> <charId> <顯示名>   只跑一個
#SBATCH --job-name=aktts-refcat
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=0-03:00
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
python -c "import pypinyin" 2>/dev/null || pip install -q pypinyin    # 文字回檢的同音字歸一要用
if [ $# -ge 3 ]; then
  python "$AKTTS_ROOT/ref_catalog.py" "$1" "$2" "$3"
else
  grep -v '^#' "$AKTTS_ROOT/ref_chars.tsv" | while IFS=$'\t' read -r key cid name _; do
    [ -n "$key" ] || continue
    printf '\n[refcat %s] %s %s %s\n' "$(date +%H:%M:%S)" "$key" "$cid" "$name"
    python "$AKTTS_ROOT/ref_catalog.py" "$key" "$cid" "$name" < /dev/null || echo "REFCAT_FAILED $key"
  done
fi
echo "REFCAT_ALL_DONE"
