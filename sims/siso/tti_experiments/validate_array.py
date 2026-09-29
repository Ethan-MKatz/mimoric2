#!/usr/bin/env python3
"""Array-level validation of a replayed 4x4 channel.

A power-vs-TTI plot passes even when the twin has silently destroyed the spatial
structure. Three failure modes it cannot see:
  * one SISO channel replicated across all 4 ports
  * the tx-major reshape transposed (rx/tx swapped)
  * per-element phases dropped somewhere in the replay path
All three destroy the per-element phase ramp, so that is the primary check here.

File layout (from the scenario generator's save_oai):
  rows = (tti, rx), cols = (tx, tap);  H[tti, rx, tx, tap]

Panels:
  1. per-element phase ramp -> estimated AoA vs TTI, against geometric AoA
  2. singular values of H vs TTI (dB) -- replicated SISO collapses s2..s4
  3. |R_rx| = E[h h^H] heatmap -- neither identity nor all-ones
  4. MRC gain over single antenna (expect ~10log10(4) = 6 dB)
"""
import argparse, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SPACING = 0.5          # element spacing in wavelengths (generator: horizontal_spacing=0.5)


def load_H(stem, taps, nrx=4, ntx=4, chan_dir=None):
    """Returns (H, taps). taps is inferred from the file width unless it divides evenly
    at the requested value -- the runner passes its replay tap count, which need not
    match the file's, so trusting it blindly would reject valid files."""
    d = chan_dir or os.path.join(REPO, "channel")
    R = np.loadtxt(os.path.join(d, f"{stem}_real.txt"))
    I = np.loadtxt(os.path.join(d, f"{stem}_imag.txt"))
    if R.shape != I.shape:
        sys.exit(f"real/imag shape mismatch: {R.shape} vs {I.shape}")
    if R.ndim == 1:
        R, I = R[None, :], I[None, :]
    n_rows, n_cols = R.shape
    if taps is None or n_cols != ntx * taps:
        if n_cols % ntx:
            sys.exit(f"{stem}: {n_cols} cols not divisible by ntx={ntx}")
        inferred = n_cols // ntx
        if taps is not None and taps != inferred:
            print(f"note: --taps {taps} does not match file width; using {inferred} "
                  f"taps inferred from {n_cols} cols / ntx {ntx}")
        taps = inferred
    if n_rows % nrx:
        sys.exit(f"{stem}: {n_rows} rows not a multiple of nrx={nrx}")
    H = (R + 1j * I).reshape(n_rows // nrx, nrx, ntx, taps)
    return H, taps


def dominant_tap(H):
    """Index of the tap carrying the most energy across the whole array."""
    return int(np.argmax(np.abs(H).sum(axis=(0, 1, 2))))


def aoa_from_ramp(h_col):
    """h_col: [tti, nrx] complex at the dominant tap for one tx element.
    Fit the per-element phase ramp; slope = 2*pi*SPACING*sin(theta)."""
    ph = np.angle(h_col * np.conj(h_col[:, [0]]))       # phase relative to element 0
    ph = np.unwrap(ph, axis=1)                          # unwrap across elements
    idx = np.arange(h_col.shape[1])
    idx_c = idx - idx.mean()
    slope = (ph - ph.mean(axis=1, keepdims=True)) @ idx_c / (idx_c @ idx_c)
    sin_t = np.clip(slope / (2 * np.pi * SPACING), -1.0, 1.0)
    return np.degrees(np.arcsin(sin_t)), slope


def geometric_aoa(traj_csv, rx_xy, tx_y):
    if not traj_csv or not os.path.exists(traj_csv):
        return None, None
    d = np.genfromtxt(traj_csv, delimiter=",", names=True)
    tx_x = np.atleast_1d(d["tx_x"])
    tti = np.atleast_1d(d["tti"]).astype(int)
    # bearing from the RX array to the TX, in the room plane
    return tti, np.degrees(np.arctan2(tx_y - rx_xy[1], tx_x - rx_xy[0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stem", default="signal_concrete_4x4_blocker")
    ap.add_argument("--taps", type=int, default=None, help="override; inferred from file width if omitted or mismatched")
    ap.add_argument("--nrx", type=int, default=4)
    ap.add_argument("--ntx", type=int, default=4)
    ap.add_argument("--chan-dir", default=None)
    ap.add_argument("--traj", default=None, help="trajectories.csv for the geometric AoA line")
    ap.add_argument("--rx-xy", default="-0.35,0.30", help="RX array x,y relative to room centre")
    ap.add_argument("--tx-y", type=float, default=-0.20)
    ap.add_argument("--show", action="store_true", help="also open the figure (needs a display)")
    ap.add_argument("--out", default=os.path.join(REPO, "logs", "array_validation.png"))
    a = ap.parse_args()

    H, taps = load_H(a.stem, a.taps, a.nrx, a.ntx, a.chan_dir)
    n_tti = H.shape[0]
    dt = dominant_tap(H)
    Hd = H[:, :, :, dt]                                  # [tti, nrx, ntx]
    print(f"{a.stem}: {n_tti} TTIs, {a.nrx}x{a.ntx}, {taps} taps, dominant tap {dt}")

    fig = plt.figure(figsize=(14, 11), dpi=140)
    gs = fig.add_gridspec(3, 2, height_ratios=[1.15, 1, 1])
    fig.suptitle(f"Array validation — '{a.stem}', {a.nrx}x{a.ntx}, {taps} taps, dominant tap {dt}", fontsize=13)

    # ---- 1. phase ramp -> AoA -------------------------------------------------
    ax = fig.add_subplot(gs[0, :])
    aoa, slope = aoa_from_ramp(Hd[:, :, 0])
    ax.plot(np.arange(n_tti), aoa, lw=1.0, color="tab:blue", label="estimated AoA (phase ramp, tx0)")
    tti_g, aoa_g = geometric_aoa(a.traj, [float(x) for x in a.rx_xy.split(",")], a.tx_y)
    if aoa_g is not None:
        ax.plot(tti_g, aoa_g, lw=1.4, color="k", ls="--", label="geometric AoA (trajectories.csv)")
    ax.set_ylabel("AoA (deg)"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    flat = np.std(slope) < 1e-6
    ax.set_title(f"PRIMARY: per-element phase ramp -> AoA   |slope| mean={np.mean(np.abs(slope)):.3f} rad/elem, "
                 f"std={np.std(slope):.3f}"
                 + ("   *** FLAT: array phases missing (SISO replicated) ***" if flat else ""),
                 fontsize=9, loc="left", color=("firebrick" if flat else "black"))

    # ---- 2. singular values ---------------------------------------------------
    ax = fig.add_subplot(gs[1, 0])
    sv = np.linalg.svd(Hd, compute_uv=False)             # [tti, min(nrx,ntx)]
    svdb = 20 * np.log10(np.maximum(sv, 1e-12))
    for k in range(sv.shape[1]):
        ax.plot(svdb[:, k], lw=.9, label=f"$\\sigma_{k+1}$")
    ax.set_ylabel("singular value (dB)"); ax.set_xlabel("TTI"); ax.grid(alpha=.3); ax.legend(fontsize=7, ncol=2)
    spread = float(np.median(svdb[:, 0] - svdb[:, -1]))
    ax.set_title(f"singular values — median $\\sigma_1/\\sigma_{{last}}$ = {spread:.1f} dB"
                 + ("   *** collapsed: rank-1 ***" if spread > 100 else ""), fontsize=9, loc="left")

    # ---- 3. |R_rx| ------------------------------------------------------------
    ax = fig.add_subplot(gs[1, 1])
    h = Hd.reshape(n_tti * a.ntx, a.nrx) if a.ntx > 1 else Hd[:, :, 0]
    Rr = (h.conj().T @ h) / h.shape[0]
    d = np.sqrt(np.real(np.diag(Rr)))
    Rn = np.abs(Rr) / np.outer(d, d)
    im = ax.imshow(Rn, vmin=0, vmax=1, cmap="viridis")
    for i in range(a.nrx):
        for j in range(a.nrx):
            ax.text(j, i, f"{Rn[i,j]:.2f}", ha="center", va="center",
                    color="w" if Rn[i, j] < .6 else "k", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=.046)
    off = Rn[~np.eye(a.nrx, dtype=bool)]
    ax.set_title(f"$|R_{{rx}}|$ — off-diag mean {off.mean():.2f}"
                 + ("   *** all-ones: replicated ***" if off.mean() > .99 else ""), fontsize=9, loc="left")
    ax.set_xlabel("rx element"); ax.set_ylabel("rx element")

    # ---- 4. MRC gain ----------------------------------------------------------
    ax = fig.add_subplot(gs[2, :])
    p_all = (np.abs(Hd) ** 2).sum(axis=1)                # combine over rx -> [tti, ntx]
    p_one = (np.abs(Hd[:, 0, :]) ** 2)
    g = 10 * np.log10(np.maximum(p_all.sum(axis=1), 1e-30) / np.maximum(p_one.sum(axis=1), 1e-30))
    ax.plot(g, lw=1.0, color="tab:purple")
    ax.axhline(10 * np.log10(a.nrx), color="k", ls="--", lw=1.2,
               label=f"ideal {10*np.log10(a.nrx):.2f} dB")
    ax.set_ylabel("MRC gain (dB)"); ax.set_xlabel("TTI"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    ax.set_title(f"MRC over single antenna — mean {g.mean():.2f} dB", fontsize=9, loc="left")

    fig.tight_layout(rect=[0, 0, 1, .97])
    fig.savefig(a.out)
    if a.show:
        try:
            os.system(f"xdg-open {a.out} >/dev/null 2>&1 &")
        except Exception:
            pass

    # ---------------- terminal verdict ----------------
    slope_std = float(np.std(slope))
    slope_abs = float(np.mean(np.abs(slope)))
    mrc = float(g.mean())
    offm = float(off.mean())
    ideal_mrc = 10 * np.log10(a.nrx)

    checks = []
    checks.append((
        "phase ramp present",
        f"slope std {slope_std:.3f} rad/elem",
        slope_std > 0.05,
        "FLAT -> array phases dropped; twin is SISO replicated across ports"))
    checks.append((
        "ramp magnitude sane",
        f"|slope| mean {slope_abs:.3f} rad/elem (max pi={np.pi:.3f})",
        slope_abs < 1.5 * np.pi,
        "slope far past pi -> wrong element spacing or wrong assumed carrier"))
    checks.append((
        "spatial modes distinct",
        f"sigma1/sigma_last {spread:.1f} dB",
        spread < 100,
        "sigma2..N at the numerical floor -> rank-1, one channel replicated"))
    checks.append((
        "rx correlation plausible",
        f"|R_rx| off-diag mean {offm:.3f}",
        0.05 < offm < 0.99,
        "~1.00 means identical elements; ~0.00 means implausibly uncorrelated at lambda/2"))
    checks.append((
        "MRC gain ~ 10log10(N)",
        f"{mrc:.2f} dB vs ideal {ideal_mrc:.2f} dB",
        abs(mrc - ideal_mrc) < 2.0,
        "combining gain off -> per-element powers or phases not independent"))

    if aoa_g is not None:
        n = min(len(aoa), len(aoa_g))
        est, geo = aoa[:n], aoa_g[:n]
        # A raw correlation here is dominated by TTIs where the strongest tap is a
        # reflection rather than the LoS path -- the ramp is real but points elsewhere.
        # Median-filter first, and report how often the estimate lands near geometry.
        w = 15
        med = np.array([np.median(est[max(0, i - w): i + w + 1]) for i in range(n)])
        r = float(np.corrcoef(med, geo)[0, 1]) if n > 2 else float("nan")
        within = float(np.mean(np.abs(med - geo) < 20.0))
        checks.append((
            "AoA tracks geometry",
            f"corr(median-filt, geometric) = {r:+.3f}, {100*within:.0f}% within 20 deg",
            ((r > 0.3) or (within > 0.5)) if r == r else False,
            "strongly negative -> element order / array axis reversed; ~0 with low hit-rate -> no spatial info"))

    width = max(len(c[0]) for c in checks)
    npass = sum(1 for c in checks if c[2])
    print()
    print("=" * 72)
    print(f"ARRAY VALIDATION  '{a.stem}'   {a.nrx}x{a.ntx}, {taps} taps, dominant tap {dt}")
    print("=" * 72)
    for name, val, ok, why in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}]  {name:<{width}}  {val}")
        if not ok:
            print(f"          -> {why}")
    print("-" * 72)
    print(f"  {npass}/{len(checks)} checks passed"
          + ("   ARRAY STRUCTURE OK" if npass == len(checks) else "   *** REVIEW FAILURES ABOVE ***"))
    print(f"  figure: {a.out}")
    print("=" * 72)
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
