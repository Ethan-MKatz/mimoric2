#!/bin/bash
# Compare the UE's MEASURED complex channel against the generator's source file,
# and write the 6-panel validation figure.
#
#   ./compare_twin.sh [plot/ue1_64] [scenario-dir] [material]
set -u
D="${1:-plot/ue1_64}"
SRC="${2:-/home/wayslab/Jamming_simulation/box_moving_tx}"
MAT="${3:-concrete}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO=/home/wayslab/tinytwin-oai

# the dump: prefer the collected copy, fall back to the live log
DUMP="$D/dl_csi_ue1.txt"
[ -s "$DUMP" ] || DUMP="$REPO/logs/dl_csi_ue1.txt"
if [ ! -s "$DUMP" ]; then
  echo "ERROR: no CSI dump with data."
  echo "  looked in: $D/dl_csi_ue1.txt and $REPO/logs/dl_csi_ue1.txt"
  echo "  CSI-RS reporting may not have run. Check:  docker logs tt-ue1 | grep 'DL CSI dump'"
  exit 1
fi
echo "== dump: $DUMP  ($(wc -l < "$DUMP") records) =="
echo

NPY="$D/twin_measured.npy"
mkdir -p "$D"
python3 "$HERE/csi_to_npy.py" "$DUMP" -o "$NPY" --taps 64 || exit 1
echo

VM=/home/wayslab/Jamming_simulation/validate_mimo.py
[ -f "$VM" ] || { echo "ERROR: $VM not found"; exit 1; }
OUT="$(cd "$D" && pwd)/twin_vs_source.png"
python3 "$VM" "$SRC" "$(cd "$D" && pwd)/twin_measured.npy" \
    --labels source,twin-measured --mat "$MAT" \
    --tap 64 --nb-rx 4 --nb-tx 4 --save "$OUT" || exit 1
echo
echo "=================================================================="
echo "figure : $OUT"
echo "npy    : $NPY"
echo
echo "Positional A/B above is EXPECTED to show ~0 dB for every hypothesis:"
echo "  CSI reports arrive ~1/100 s while the tap file loops every 800 TTIs,"
echo "  so snapshot k is unrelated to source TTI k. Ignore its verdict --"
echo "  including any 'conjugated fits better' warning. Use the alignment below."
echo
echo "=================================================================="

echo
echo "=================== TIME-ALIGNED COMPARISON ======================"
python3 "$HERE/align_twin.py" --npy "$NPY" || exit 1
echo
echo "What good looks like:"
echo "  correlation > 0.85 per snapshot, and ONE tap shift shared by all of"
echo "  them (that shift is receiver timing, not an error)."
echo "  NMSE lands near 10*log10(1-corr^2): ~-7 dB at corr 0.90. The CSI-RS"
echo "  estimate is interpolated and carries no pre-cursor taps, so it is not"
echo "  a clean sample of H -- judge the replay on correlation, the tap"
echo "  profile past the dominant tap, and the spatial metrics."
echo "=================================================================="
