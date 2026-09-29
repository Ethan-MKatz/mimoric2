#!/bin/bash
# Live status for a demo1 run: script, containers, logs, channel data, crash core.
REPO=/home/wayslab/tinytwin-oai
while true; do
  clear
  echo "===== $(date '+%H:%M:%S') ====================================="
  if pgrep -f tti_multiue_experiments_demo1 >/dev/null; then
    P=$(pgrep -f tti_multiue_experiments_demo1 | head -1)
    echo "script   : RUNNING (pid $P, elapsed $(ps -o etime= -p $P | tr -d ' '))"
  else
    echo "script   : NOT RUNNING"
  fi
  echo
  echo "--- containers ---"
  docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E 'tt-gnb|tt-ue|edgeric' | sed 's/^/  /'
  echo
  echo "--- channel data ---"
  for f in "$REPO"/logs/dl_channel_ue*.txt; do
    [ -e "$f" ] && echo "  $(basename $f): $(wc -l < $f) lines"
  done
  ls "$REPO"/sims/siso/tti_experiments/edgeric-v2/results/ul_channel_*.txt >/dev/null 2>&1 \
    && echo "  ul_channel: $(cat $REPO/sims/siso/tti_experiments/edgeric-v2/results/ul_channel_power_*.txt 2>/dev/null | wc -l) rows"
  echo "  DL RANK samples: $(grep -c 'DL RANK' $REPO/logs/snr.txt 2>/dev/null)"
  echo
  echo "--- gNB (last 3) ---"
  docker logs --tail 3 tt-gnb 2>&1 | cut -c1-110 | sed 's/^/  /'
  echo
  echo "--- UE (last 3) ---"
  docker logs --tail 3 tt-ue1 2>&1 | cut -c1-110 | sed 's/^/  /'
  echo
  if ls "$REPO"/logs/core.* >/dev/null 2>&1; then
    echo ">>> CORE DUMP PRESENT <<<"; ls -la "$REPO"/logs/core.* | sed 's/^/  /'
  else
    echo "core     : none yet"
  fi
  sleep 5
done
