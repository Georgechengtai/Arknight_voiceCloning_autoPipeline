#!/usr/bin/env bash
# 把回聽對齊的作業送上叢集並取回結果（只做語音辨識；音檔只傳到自己的叢集）。
# 用法：bash tools/voice_cluster.sh <scene> blocks|lines        （需先連上 CUHK VPN）
#   blocks：傳 voice_work/upload_blocks/（ElevenLabs 各段），結果存成 voice_work/align.json
#   lines ：傳 voice_work/upload_lines/（切好的逐句檔），結果存成 voice_work/align_lines.json
# 全程重用同一條 SSH 連線，查作業狀態每 60 秒一次（叢集會封鎖頻繁連線的來源位址，見 cluster/ENV.md）。
set -euo pipefail
cd "$(dirname "$0")/.."
scene=$1; what=$2
case $what in blocks) out=align.json ;; lines) out=align_lines.json ;; *) echo "第二個參數要是 blocks 或 lines"; exit 1 ;; esac
work=out/$scene/voice_work
remote="large-data/aktts/work/scenes/${scene}_voice_$what"
SSH=(ssh -o ControlMaster=auto -o "ControlPath=$HOME/.ssh/cm-%r@%h-%p" -o ControlPersist=2h -o BatchMode=yes scrp)

"${SSH[@]}" "mkdir -p ~/$remote && rm -f ~/$remote/align.json"
tar cf - -C cluster voice_align.py voice_align.sh | "${SSH[@]}" "tar xf - -C ~/large-data/aktts"
tar cf - -C "$work/upload_$what" . | "${SSH[@]}" "tar xf - -C ~/$remote"
jobid=$("${SSH[@]}" "cd ~/large-data/aktts && sbatch --parsable voice_align.sh ~/$remote/job.json")
echo "已送出作業 $jobid"
while sleep 60; do
  state=$("${SSH[@]}" "squeue -h -j $jobid -o %T 2>/dev/null || true")
  echo "$(date +%H:%M:%S) ${state:-結束}"
  [ -z "$state" ] && break
done
"${SSH[@]}" "tail -n 3 ~/large-data/aktts/aktts-valign-$jobid.log"
"${SSH[@]}" "cat ~/$remote/align.json" > "$work/$out.tmp" && mv "$work/$out.tmp" "$work/$out"
echo "取回 $work/$out（作業 $jobid）"
