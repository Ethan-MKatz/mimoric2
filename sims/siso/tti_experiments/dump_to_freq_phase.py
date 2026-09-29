#!/usr/bin/env python3
"""Expand a raw channel dump into a readable per-frequency table.

The dumps (dl_csi_ue1.txt, ul_srs_gnb.txt) already hold frequency AND phase --
each value is a complex number for one antenna pair at one RB -- but they store
it as bare `re im` integers with the position implied by field order.  This
writes the same data out with every axis named, plus amplitude and phase.

    rec frame slot rx tx rb freq_MHz real imag amp_dB phase_deg

  rx / tx    DL: rx = UE antenna, tx = gNB CSI-RS port
             UL: rx = gNB antenna, tx = UE SRS port
  freq_MHz   offset from carrier centre; RB 0 is the lowest frequency
  amp_dB     20*log10|H|, in the receiver's own fixed-point units (~54 dB
             above the channel file) -- compare ratios, not absolute levels
  phase_deg  atan2(imag, real), wrapped to (-180, 180]

Nothing is normalised, aligned or gain-fitted: this is the measurement as the
receiver wrote it.

    python3 dump_to_freq_phase.py plot/ue1_64/dl_csi_ue1.txt -o dl_freq_phase.txt
    python3 dump_to_freq_phase.py plot/ue1_64/ul_srs_gnb.txt -o ul_freq_phase.txt
    ... --rec 15 --tx 0        # one snapshot, one transmit port
"""
import argparse
import sys
import numpy as np

SCS_HZ = 30e3
RB_HZ = 12 * SCS_HZ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--rec", type=int, default=None, help="only this record")
    ap.add_argument("--tx", type=int, default=None, help="only this transmit port")
    ap.add_argument("--rx", type=int, default=None, help="only this receive antenna")
    a = ap.parse_args()

    rows_out = 0
    with open(a.dump) as fin, open(a.out, "w") as f:
        head = None
        for line in fin:
            w = line.split()
            if not w or w[0] not in ("CSI", "SRS"):
                continue
            rec, frame, slot = int(w[1]), int(w[2]), int(w[3])
            nrx, ntx, nsc = int(w[4]), int(w[5]), int(w[6])
            v = np.asarray(w[7:], dtype=np.float64)
            if v.size < nrx * ntx * nsc * 2:
                continue
            if a.rec is not None and rec != a.rec:
                continue
            H = (v[: nrx * ntx * nsc * 2:2] + 1j * v[1: nrx * ntx * nsc * 2:2]).reshape(nrx, ntx, nsc)

            if head is None:
                head = (nrx, ntx, nsc)
                # RB 0 sits at the bottom of the band, so centre the axis on it.
                freq = (np.arange(nsc) - (nsc - 1) / 2) * RB_HZ / 1e6
                dirn = "DOWNLINK CSI-RS (rx = UE ant, tx = gNB port)" if w[0] == "CSI" \
                       else "UPLINK SRS (rx = gNB ant, tx = UE port)"
                f.write(f"# {dirn}\n")
                f.write(f"# source: {a.dump}\n")
                f.write(f"# {nrx} rx x {ntx} tx x {nsc} RB per record; RB spacing {RB_HZ/1e6:.3f} MHz\n")
                f.write("# amp_dB is in receiver fixed-point units (~54 dB above the channel file)\n")
                f.write("rec frame slot rx tx rb freq_MHz real imag amp_dB phase_deg\n")

            amp = 20 * np.log10(np.abs(H) + 1e-12)
            ph = np.degrees(np.angle(H))
            for r in range(nrx):
                if a.rx is not None and r != a.rx:
                    continue
                for t in range(ntx):
                    if a.tx is not None and t != a.tx:
                        continue
                    for k in range(nsc):
                        f.write(f"{rec} {frame} {slot} {r} {t} {k} {freq[k]:+8.3f} "
                                f"{H[r,t,k].real:.0f} {H[r,t,k].imag:.0f} "
                                f"{amp[r,t,k]:8.3f} {ph[r,t,k]:+8.2f}\n")
                        rows_out += 1

    if head is None:
        sys.exit(f"{a.dump}: no usable records")
    print(f"wrote {a.out}  ({rows_out} rows, {head[0]} rx x {head[1]} tx x {head[2]} RB)")


if __name__ == "__main__":
    main()
