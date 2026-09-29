#!/usr/bin/env python3
"""Loopback: replace the radio with a perfect wire and re-run the real plotting code.

The question this answers:

    "Are the ground-truth curves really the ground truth, and is the measured
     curve computed the same way?"

Method. Take the channel file, compute what a PERFECT receiver would report -- the
channel's own frequency response at the 106 RB bins -- and write it out in the exact
text format the UE writes. Then run the unmodified pipeline on it:

    synthetic dump -> csi_to_npy -> export_aligned -> plot_channel_freq

If the two plotting paths are equivalent, the dashed "measured" curve must land on
top of the solid "ground truth" curve, to the quantisation floor. Any gap is
asymmetry between the two paths -- a plotting bug, not the radio.

No measured data is used. No comparison against any existing plot.

    python3 review/loopback_test.py
"""
import os
import subprocess
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
REPO = "/home/wayslab/tinytwin-oai"
STEM = "signal_metal_4x4"
OUT = os.path.join(EXP, "plot", "loopback")

N_FFT, N_RB, SCS = 2048, 106, 30e3
FCO = N_FFT - (N_RB * 12) // 2
BINS = [(FCO + 12 * rb) % N_FFT for rb in range(N_RB)]
TTIS = [14, 102, 171, 262, 331, 438, 526, 651]      # arbitrary spread, nothing special
INT_MAX = 20000.0                                    # realistic int16 dump magnitude


def main():
    os.makedirs(OUT, exist_ok=True)
    R = np.loadtxt(f"{REPO}/channel/{STEM}_real.txt")
    I = np.loadtxt(f"{REPO}/channel/{STEM}_imag.txt")
    S = (R + 1j * I).reshape(-1, 4, 4, 64)
    Sf = np.fft.fft(S, N_FFT, axis=-1)[..., BINS]    # the truth, at the dumped bins

    scale = INT_MAX / np.abs(Sf[TTIS]).max()
    dump = os.path.join(OUT, "dl_csi_ue1.txt")
    with open(dump, "w") as f:
        for rec, t in enumerate(TTIS):
            H = np.round(Sf[t] * scale)              # int16, as the UE writes
            f.write(f"CSI {rec} {100 + 8*rec} 0 4 4 {N_RB}")
            for rx in range(4):
                for tx in range(4):
                    for k in range(N_RB):
                        f.write(f" {int(H[rx,tx,k].real)} {int(H[rx,tx,k].imag)}")
            f.write("\n")
    print(f"wrote {dump}: {len(TTIS)} perfect-receiver records from {STEM}")
    print(f"quantisation floor: 1 LSB on a peak of {INT_MAX:.0f} = "
          f"{20*np.log10(1/INT_MAX):.1f} dB below full scale\n")

    py = sys.executable
    for cmd in ([py, f"{EXP}/csi_to_npy.py", dump, "-o", f"{OUT}/twin_measured.npy", "--taps", "64"],
                [py, f"{EXP}/export_aligned.py", "--npy", f"{OUT}/twin_measured.npy",
                 "--stem", STEM, "--outdir", OUT],
                [py, f"{EXP}/plot_channel_freq.py", "--dir", OUT, "--stem", STEM,
                 "--out", f"{OUT}/channel_freq_loopback.png"]):
        if subprocess.run(cmd).returncode != 0:
            sys.exit(f"step failed: {cmd[1]}")

    # ---- reproduce EXACTLY what the figure draws, and measure the gap -------
    sys.path.insert(0, EXP)
    from plot_channel_freq import load_dump, detrend_phase
    M, _ = load_dump(dump)
    rows = np.atleast_2d(np.loadtxt(f"{OUT}/align_summary.txt", comments="#"))
    n = min(len(M), len(rows))
    num = (np.abs(Sf[rows[:n, 1].astype(int)]) ** 2).sum(axis=(1, 2, 3)) ** .5
    den = (np.abs(M[:n]) ** 2).sum(axis=(1, 2, 3)) ** .5
    M = M[:n] * (num / den)[:, None, None, None]     # plot_channel_freq.py:142-151
    fr = (np.arange(N_RB) - (N_RB - 1) / 2) * 12 * SCS / 1e6

    da, dp, bad = [], [], 0
    for i in range(n):
        t = int(rows[i, 1])
        if t not in TTIS:
            bad += 1
            continue
        for rx in range(4):
            for tx in range(4):
                s, m = Sf[t, rx, tx], M[i, rx, tx]
                da.append(20 * np.log10(np.abs(m) + 1e-30) - 20 * np.log10(np.abs(s) + 1e-30))
                dp.append(detrend_phase(m, fr) - detrend_phase(s, fr))
    da, dp = np.abs(np.concatenate(da)), np.abs(np.concatenate(dp))

    print(f"\n{'='*66}\nMEASURED-PATH OUTPUT vs GROUND-TRUTH-PATH OUTPUT, same figure")
    print(f"  snapshots matched to the right source TTI : {n - bad} of {n}")
    print(f"  magnitude gap : median {np.median(da):.4f} dB   p99 {np.percentile(da,99):.4f} dB   max {da.max():.4f} dB")
    print(f"  phase gap     : median {np.median(dp):.4f} deg  p99 {np.percentile(dp,99):.4f} deg  max {dp.max():.4f} deg")
    verdict = "PASS -- the two paths are equivalent" if (np.median(da) < 0.01 and np.median(dp) < 0.05) \
              else "**FAIL** -- the paths differ by more than quantisation"
    print(f"  {verdict}\n{'='*66}")


if __name__ == "__main__":
    main()
