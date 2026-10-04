#!/usr/bin/env bash
# 從叢集取回各角色的參考音摘要（不含台詞原文與音檔），放到 config/refs/<短名>.json。
# 用法：在倉庫根目錄執行 bash tools/refs_pull.sh        （需先連上 CUHK VPN；只開一次 SSH 連線）
set -euo pipefail
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
ssh -o ControlMaster=auto -o ControlPath="$HOME/.ssh/cm-%r@%h-%p" -o ControlPersist=2h scrp \
  'cd ~/large-data/aktts/work/refs && tar cf - */summary.json' | tar xf - -C "$tmp"
mkdir -p config/refs
for d in "$tmp"/*/; do
  cp "$d/summary.json" "config/refs/$(basename "$d").json"
done
rm -rf "$tmp"
python3 - <<'E'
import glob, json
for p in sorted(glob.glob("config/refs/*.json")):
    d = json.load(open(p, encoding="utf-8"))
    keys = set().union(*(set(r) for r in d["refs"] + d["clips"]))
    assert not keys & {"text", "asr", "path"}, f"{p} 含有不該入庫的欄位"
    print(p, d["stats"]["n_usable"], "段可用")
E
