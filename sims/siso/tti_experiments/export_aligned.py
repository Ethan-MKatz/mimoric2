#!/usr/bin/env python3
r"""Export the time-aligned twin-vs-source comparison as plain text.

Writes three space-separated files with '#' header lines, loadable by
numpy.loadtxt, pandas.read_csv(sep=r'\s+'), gnuplot, Excel, MATLAB.

  align_summary.txt   one row per CSI snapshot
  tap_profile.txt     mean energy per tap, source vs twin
  aligned_H.txt       the full complex channel, both sides, long format
"""
import argparse, os
import numpy as np

REPO = "/home/wayslab/tinytwin-oai"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npy", default="plot/ue1_64/twin_measured.npy")
    ap.add_argument("--stem", default="signal_concrete_4x4_blocker")
    ap.add_argument("--chan-dir", default=f"{REPO}/channel")
    ap.add_argument("--outdir", default="plot/ue1_64")
    ap.add_argument("--tag", default="", help="suffix for output names, e.g. _ul")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    R = np.loadtxt(f"{a.chan_dir}/{a.stem}_real.txt")
    I = np.loadtxt(f"{a.chan_dir}/{a.stem}_imag.txt")
    S = (R + 1j * I).reshape(-1, 4, 4, 64)
    T = np.load(a.npy)
    nrec, nrx, ntx, ntap = T.shape

    A, B = np.fft.fft(S, axis=-1), np.fft.fft(T, axis=-1)
    nA = np.sqrt((np.abs(A) ** 2).sum(axis=(1, 2, 3)))
    nB = np.sqrt((np.abs(B) ** 2).sum(axis=(1, 2, 3)))
    k = np.arange(ntap)

    rows, src_al, twn_al = [], [], []
    for n in range(nrec):
        X = (A * np.conj(B[n])).sum(axis=(1, 2))
        C = np.abs(np.fft.ifft(X, axis=-1)) * ntap / (nA[:, None] * nB[n] + 1e-30)
        s, d = np.unravel_index(np.argmax(C), C.shape)
        Bs = np.fft.ifft(B[n] * np.exp(-2j * np.pi * k * d / ntap), axis=-1)
        al = (S[s] * np.conj(Bs)).sum() / ((np.abs(Bs) ** 2).sum() + 1e-30)
        Bs = al * Bs
        nmse = 10 * np.log10((np.abs(Bs - S[s]) ** 2).sum() / (np.abs(S[s]) ** 2).sum())
        rows.append((n, s, d, C[s, d], nmse, np.abs(al), np.degrees(np.angle(al))))
        src_al.append(S[s]); twn_al.append(Bs)
    src_al, twn_al = np.array(src_al), np.array(twn_al)

    # ---- 1. per-snapshot summary
    p1 = os.path.join(a.outdir, f"align_summary{a.tag}.txt")
    with open(p1, "w") as f:
        f.write("# time-aligned twin-vs-source, one row per CSI-RS snapshot\n")
        f.write("# src_tti  : source TTI this snapshot best matches (file loops every 800)\n")
        f.write("# tap_shift: receiver timing offset in taps; should be the SAME for all rows\n")
        f.write("# corr     : normalised complex correlation, 0..1\n")
        f.write("# nmse_dB  : after gain alignment; tracks 10*log10(1-corr^2)\n")
        f.write("# gain_abs, gain_deg: complex scale relating twin to source\n")
        f.write("# record src_tti tap_shift corr nmse_dB gain_abs gain_deg\n")
        for r in rows:
            f.write(f"{r[0]:d} {r[1]:d} {r[2]:d} {r[3]:.4f} {r[4]:.2f} {r[5]:.6e} {r[6]:.2f}\n")

    # ---- 2. tap energy profile
    es = (np.abs(src_al) ** 2).mean(axis=(0, 1, 2))
    et = (np.abs(twn_al) ** 2).mean(axis=(0, 1, 2))
    p2 = os.path.join(a.outdir, f"tap_profile{a.tag}.txt")
    with open(p2, "w") as f:
        f.write("# mean energy per tap, averaged over snapshots and antenna pairs\n")
        f.write("# both normalised so the strongest tap is 0 dB\n")
        f.write("# tap source_dB twin_dB delta_dB\n")
        for t in range(ntap):
            a_ = 10 * np.log10(es[t] / es.max() + 1e-20)
            b_ = 10 * np.log10(et[t] / et.max() + 1e-20)
            f.write(f"{t:d} {a_:.3f} {b_:.3f} {b_ - a_:.3f}\n")

    # ---- 3. full complex channel, long format
    p3 = os.path.join(a.outdir, f"aligned_H{a.tag}.txt")
    with open(p3, "w") as f:
        f.write("# aligned complex channel: source vs measured twin\n")
        f.write("# twin values are shifted by tap_shift and gain-aligned, so the two\n")
        f.write("# columns are directly comparable\n")
        f.write("# record src_tti rx tx tap src_re src_im twin_re twin_im\n")
        for n in range(nrec):
            s = rows[n][1]
            for r in range(nrx):
                for t in range(ntx):
                    for l in range(ntap):
                        u, v = src_al[n, r, t, l], twn_al[n, r, t, l]
                        f.write(f"{n} {s} {r} {t} {l} "
                                f"{u.real:.6e} {u.imag:.6e} {v.real:.6e} {v.imag:.6e}\n")

    for p in (p1, p2, p3):
        print(f"wrote {p}  ({sum(1 for _ in open(p))} lines)")


if __name__ == "__main__":
    main()
