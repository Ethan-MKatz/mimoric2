#!/usr/bin/env python3
"""Align each measured CSI snapshot to the source TTI it actually replayed.

The rfsimulator walks the tap file one line per TTI and rewinds at EOF, while
CSI-RS reports arrive far more slowly -- so snapshot k has no relation to source
TTI k, and a positional A/B compares unrelated instants.  Here we search every
source TTI and every cyclic tap shift (receiver timing offset) for the best
complex match, then report NMSE at that alignment.
"""
import argparse
import numpy as np

REPO = "/home/wayslab/tinytwin-oai"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npy", default="plot/ue1_64/twin_measured.npy")
    ap.add_argument("--stem", default="signal_concrete_4x4_blocker")
    ap.add_argument("--chan-dir", default=f"{REPO}/channel")
    a = ap.parse_args()

    R = np.loadtxt(f"{a.chan_dir}/{a.stem}_real.txt")
    I = np.loadtxt(f"{a.chan_dir}/{a.stem}_imag.txt")
    S = (R + 1j * I).reshape(-1, 4, 4, 64)
    T = np.load(a.npy)
    print(f"source {S.shape}   twin {T.shape}\n")

    A = np.fft.fft(S, axis=-1)                      # [800,4,4,64]
    B = np.fft.fft(T, axis=-1)                      # [n,4,4,64]
    nA = np.sqrt((np.abs(A) ** 2).sum(axis=(1, 2, 3)))
    nB = np.sqrt((np.abs(B) ** 2).sum(axis=(1, 2, 3)))

    print(f"{'rec':>4} {'src TTI':>8} {'tap shift':>10} {'corr':>7} {'NMSE dB':>9}")
    ttis, corrs, nmses = [], [], []
    for n in range(B.shape[0]):
        # cross-power summed over antennas, then IFFT over subcarriers -> all tap shifts at once
        X = (A * np.conj(B[n])).sum(axis=(1, 2))    # [800,64]
        C = np.abs(np.fft.ifft(X, axis=-1)) * 64    # [800,64] correlation vs (tti, shift)
        C = C / (nA[:, None] * nB[n] + 1e-30)
        s, d = np.unravel_index(np.argmax(C), C.shape)
        corr = C[s, d]
        # align B[n] onto S[s] with that shift, then gain-align and measure NMSE
        k = np.arange(64)
        Bs = np.fft.ifft(B[n] * np.exp(-2j * np.pi * k * d / 64), axis=-1)
        alpha = (S[s] * np.conj(Bs)).sum() / ((np.abs(Bs) ** 2).sum() + 1e-30)
        nmse = 10 * np.log10((np.abs(alpha * Bs - S[s]) ** 2).sum() /
                             (np.abs(S[s]) ** 2).sum())
        print(f"{n:>4} {s:>8} {d:>10} {corr:>7.3f} {nmse:>9.1f}")
        ttis.append(s); corrs.append(corr); nmses.append(nmse)

    corrs, nmses, ttis = np.array(corrs), np.array(nmses), np.array(ttis)
    print(f"\nmedian correlation {np.median(corrs):.3f}   median NMSE {np.median(nmses):.1f} dB")
    print(f"tap shift spread: {np.ptp(ttis)} TTIs used, "
          f"{len(set(ttis))} distinct source TTIs matched")
    good = (corrs > 0.9).sum()
    print(f"{good}/{len(corrs)} snapshots match a source TTI with correlation > 0.9")


if __name__ == "__main__":
    main()
