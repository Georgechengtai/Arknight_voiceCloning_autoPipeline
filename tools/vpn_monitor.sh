#!/bin/bash
# 每 5 秒記錄：PIA 狀態、到 SCRP 的路由、SSH 22 埠、Claude API 是否可達。最長 90 分鐘。
LOG="$1"; END=$(( $(date +%s) + 5400 )); SSH_DONE=0
echo "time | pia | utuns | route_to_scrp | default_route | ssh22 | claude_api | note" >> "$LOG"
while [ "$(date +%s)" -lt "$END" ]; do
  T=$(date +%H:%M:%S)
  PIA=$(/usr/local/bin/piactl get connectionstate 2>/dev/null)
  UT=$(ifconfig -l | tr ' ' '\n' | grep -c -E '^(utun|gpd)')
  R1=$(route -n get 137.189.68.83 2>/dev/null | awk '/interface:/{print $2}')
  R0=$(route -n get 1.1.1.1 2>/dev/null | awk '/interface:/{print $2}')
  # SSH 埠每 60 秒才探一次：2026-10-04 每 5 秒探一次，約一分鐘後叢集就封鎖了來源位址
  if [ $(( $(date +%s) - ${LAST22:-0} )) -ge 60 ]; then
    LAST22=$(date +%s)
    if nc -z -G 3 137.189.68.83 22 >/dev/null 2>&1; then S22=OPEN; else S22=closed; fi
  fi
  CODE=$(curl -s -o /dev/null -m 6 -w '%{http_code}' https://api.anthropic.com/ 2>/dev/null); [ "$CODE" = "000" ] && CL="DOWN" || CL="ok($CODE)"
  NOTE=""
  if [ "$S22" = OPEN ] && [ "$SSH_DONE" = 0 ]; then
    NOTE="ssh-key-login: $(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -o HostName=137.189.68.83 scrp 'hostname' 2>&1 | tail -1)"; SSH_DONE=1
  fi
  echo "$T | $PIA | $UT | $R1 | $R0 | $S22 | $CL | $NOTE" >> "$LOG"
  sleep 5
done
