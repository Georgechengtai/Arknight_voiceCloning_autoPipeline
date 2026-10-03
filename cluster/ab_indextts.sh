#!/usr/bin/env bash
# 下載 IndexTTS-2 與 IndexTTS-2.5 的模型權重，各合成同一組句子供試聽對比。
# 用法： cd ~/large-data/aktts && sbatch ab_indextts.sh
#SBATCH --job-name=aktts-ab
#SBATCH --partition=scrp,gpu
#SBATCH --gpus=rtx3090
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=0-01:30
#SBATCH --output=%x-%j.log

set -euo pipefail
set +u; source "$HOME/large-data/aktts/env.sh"; set -u
SCRIPT_DIR="$AKTTS_ROOT"
cd "$AKTTS_ROOT/index-tts"
log() { printf '\n[ab %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

log "下載模型權重到 $AKTTS_ROOT/models（已下載的會跳過）"
python - <<'PY'
import os
from huggingface_hub import snapshot_download
root = os.environ["AKTTS_ROOT"]
for repo, name in (("IndexTeam/IndexTTS-2", "IndexTTS-2"), ("IndexTeam/IndexTTS-2.5", "IndexTTS-2.5")):
    p = snapshot_download(repo_id=repo, local_dir=f"{root}/models/{name}")
    print("downloaded", repo, "->", p, flush=True)
PY
du -sh "$AKTTS_ROOT"/models/*

log "取得官方示例參考音"
python -c "from indextts.utils.examples_downloader import ensure_examples_available; ensure_examples_available()"
ls examples | head -30

for ver in v2 v25; do
  log "合成：$ver"
  python "$SCRIPT_DIR/ab_indextts.py" "$ver" || echo "AB_FAILED $ver"
done
log "完成"; ls -la "$AKTTS_ROOT"/work/ab_test/*/
