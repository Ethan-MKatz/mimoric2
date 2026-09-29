#!/bin/bash
# Summarize a demo1 MIMO run.  Usage: ./summarize_run.sh [plot/ue1_64]
D="${1:-plot/ue1_64}"
REPO=/home/wayslab/tinytwin-oai
# fall back to the live logs if the run hasn't torn down yet
SNR="$D/snr.txt";      [ -s "$SNR" ] || SNR="$REPO/logs/snr.txt"
DLC=$(ls "$D"/dl_channel_ue*.txt 2>/dev/null | head -1)
[ -n "$DLC" ] || DLC=$(ls "$REPO"/logs/dl_channel_ue*.txt 2>/dev/null | head -1)
ULC=$(ls "$D"/ul_channel_power_*.txt 2>/dev/null | head -1)
[ -n "$ULC" ] || ULC=$(ls "$REPO"/sims/siso/tti_experiments/edgeric-v2/results/ul_channel_power_*.txt 2>/dev/null | head -1)

echo "================ MIMO RUN SUMMARY : $D ================"
echo
echo "--- 1. Was the 4x4 channel really replayed? (UE console) ---"
grep -h -E "channel replay:|REPLAY-DIAG" "$D"/ue1_console.log 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g;s/^/  /' \
  || echo "  (no ue1_console.log -- capture with: docker logs tt-ue1 > $D/ue1_console.log)"
echo "  ^ four DISTINCT values on the H[0] line = genuine 4x4, not replicated SISO"
echo
echo "--- 2. DL rank actually scheduled ---"
if [ -s "$SNR" ]; then
  echo "  source: $SNR"
  grep -o "DL RANK: [0-9]*" "$SNR" | sort | uniq -c | sed 's/^/  /'
else echo "  (no snr.txt)"; fi
echo
echo "--- 3. DL channel power per rx antenna (UE side, dB) ---"
if [ -n "$DLC" ] && [ -s "$DLC" ]; then
  echo "  source: $DLC"
  awk '{n++; for(i=4;i<=NF;i++){s[i]+=$i; ss[i]+=$i*$i;
        if(n==1||$i<mn[i])mn[i]=$i; if(n==1||$i>mx[i])mx[i]=$i}}
       END{for(i=4;i<=NF;i++) printf "    rx%d: mean %7.2f  std %5.2f  min %7.2f  max %7.2f\n",
           i-4,s[i]/n,sqrt(ss[i]/n-(s[i]/n)^2),mn[i],mx[i]; printf "    samples: %d\n",n}' "$DLC"
  echo "  ^ antennas that differ and vary independently = real spatial structure"
else echo "  (none)"; fi
echo
echo "--- 4. UL channel power per rx antenna (MIMO-RIC / muApp3, dB) ---"
if [ -n "$ULC" ] && [ -s "$ULC" ]; then
  echo "  source: $ULC"
  awk -F, 'NR>1{n++; s[$6]+=$7; ss[$6]+=$7*$7; c[$6]++}
       END{for(r=0;r<8;r++) if(c[r]) printf "    rx%d: mean %7.2f  std %5.2f  (%d rows)\n",
           r,s[r]/c[r],sqrt(ss[r]/c[r]-(s[r]/c[r])^2),c[r]; printf "    total rows: %d\n",n}' "$ULC"
else echo "  (none)"; fi
echo
echo "--- 5. Link quality (exact metric names from snr.txt) ---"
if [ -s "$SNR" ]; then
  while read -r m; do
    grep -oE "^$m: [0-9.-]+" "$SNR" | awk -v M="$m" '{n++;s+=$NF; if(n==1||$NF<mn)mn=$NF; if(n==1||$NF>mx)mx=$NF}
      END{if(n) printf "    %-9s mean %8.2f  min %8.2f  max %8.2f  (n=%d)\n",M,s/n,mn,mx,n}'
  done <<MEND
DL CQI
UL CQI
UL MCS
UL TPT
UL ACK
MEND
fi
echo
echo "--- 6. Files collected ---"
ls -la "$D" 2>/dev/null | tail -n +2 | sed 's/^/  /'
echo
echo "--- 7. Array validation (structural PASS/FAIL) ---"
if grep -q "ARRAY VALIDATION" plot/run*.log 2>/dev/null; then
  awk '/ARRAY VALIDATION/,/^=====.*$/' $(grep -l "ARRAY VALIDATION" plot/run*.log | tail -1) | sed 's/^/  /'
else
  echo "  not in run logs yet -- regenerate any time (does not need a live run):"
  echo "    python3 validate_array.py --stem signal_concrete_4x4 --taps 64 \\"
  echo "      --traj /home/wayslab/Jamming_simulation/box_moving_tx/trajectories.csv \\"
  echo "      --out $D/array_validation.png"
fi
echo "======================================================="
