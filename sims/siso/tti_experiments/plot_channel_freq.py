#!/usr/bin/env python3
"""Channel vs FREQUENCY: measured against ground truth, for either direction.

Frequency-domain counterpart of plot_phase_amp.py, and the same convention:
solid = source, dashed = measured.  Run by demo1 at teardown.

How the two sides are made comparable
-------------------------------------
The measurement is native frequency domain -- one complex number per RB -- so
it is used as captured, with no conversion.  The source is a 64-tap impulse
response, so it is FFT'd onto the same RB grid.

Two receiver effects are removed before comparing, because they are artefacts
rather than channel:

  * overall gain   -- one scale per SNAPSHOT (never per trace), so the
    level differences between antennas and ports are preserved.
  * bulk delay     -- the receiver syncs to the strongest path, which adds a
                      linear phase ramp across frequency. A straight line is
                      fitted and removed from BOTH sides, leaving the residual
                      shape, which is the part that carries information.

Which snapshot maps to which source TTI comes from align_summary{,_ul}.txt,
written by export_aligned.py -- so run the normal pipeline first.

    ./plot_channel_freq.py --dir plot/ue1_64            # downlink
    ./plot_channel_freq.py --dir plot/ue1_64 --ul       # uplink
"""
import argparse, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = "/home/wayslab/tinytwin-oai"
RB_HZ = 12 * 30e3          # numerology 1: one point per resource block


def load_dump(path):
    recs, meta = [], None
    for line in open(path):
        w = line.split()
        if not w or w[0] not in ("CSI", "SRS"):
            continue
        try:
            nrx, ntx, nsc = int(w[4]), int(w[5]), int(w[6])
            v = np.asarray(w[7:], dtype=np.float64)
        except ValueError:
            continue
        if v.size < nrx * ntx * nsc * 2:
            continue
        if meta is None:
            meta = (nrx, ntx, nsc)
        elif meta != (nrx, ntx, nsc):
            continue
        v = v[: nrx * ntx * nsc * 2]
        recs.append((v[0::2] + 1j * v[1::2]).reshape(nrx, ntx, nsc))
    if not recs:
        sys.exit(f"{path}: no usable records")
    return np.array(recs), meta


def both_legends(ax, tti, loc_colour="upper right", loc_style="lower left"):
    """Two legends on one axis: which colour is which antenna, and which line
    style is ground truth vs measured. ax.legend() REPLACES any previous legend,
    so the colour one must be re-added as an artist before the style one is made."""
    from matplotlib.lines import Line2D
    colour = ax.legend(fontsize=7.5, ncol=2, loc=loc_colour, framealpha=.9,
                       title=f"source TTI {tti} of 800", title_fontsize=7.5)
    ax.add_artist(colour)
    h = [Line2D([], [], color="0.25", lw=1.9, ls="-"),
         Line2D([], [], color="0.25", lw=1.5, ls="--")]
    ax.legend(h, ["GROUND TRUTH  (channel file)", "MEASURED  (after replay)"],
              fontsize=7.5, loc=loc_style, framealpha=.9)


def detrend_phase(H, f):
    """Unwrap, then remove the best-fit linear ramp -- that ramp is bulk delay."""
    ph = np.unwrap(np.angle(H))
    a = np.polyfit(f, ph, 1)
    return np.degrees(ph - np.polyval(a, f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="plot/ue1_64")
    ap.add_argument("--ul", action="store_true", help="uplink SRS instead of downlink CSI-RS")
    ap.add_argument("--stem", default="signal_concrete_4x4_blocker")
    ap.add_argument("--chan-dir", default=f"{REPO}/channel")
    ap.add_argument("--gain", choices=("band", "taps"), default="band",
                    help="how the one-per-snapshot scale is fitted; see comment in main()")
    ap.add_argument("--rec", default="median",
                    help="snapshot to draw: an index, or best/median/worst by correlation. "
                         "Default is median -- picking 'best' shows a favourable moment "
                         "(correlation tracks level at +0.34, and the best-correlating "
                         "snapshot sits near the 88th percentile of level).")
    ap.add_argument("--tx", type=int, default=0)
    ap.add_argument("--rx", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    dump = os.path.join(a.dir, "ul_srs_gnb.txt" if a.ul else "dl_csi_ue1.txt")
    summ = os.path.join(a.dir, "align_summary_ul.txt" if a.ul else "align_summary.txt")
    for p in (dump, summ):
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            sys.exit(f"missing or empty: {p}\nrun the normal pipeline first")
    RXN, TXN = ("gNB", "UE") if a.ul else ("UE", "gNB")
    label = "UPLINK SRS" if a.ul else "DOWNLINK CSI-RS"
    a.out = a.out or os.path.join(a.dir, f"channel_freq_{'ul' if a.ul else 'dl'}.png")

    M, (nrx, ntx, nsc) = load_dump(dump)
    rows = np.loadtxt(summ, comments="#")
    rows = np.atleast_2d(rows)
    n = min(len(M), len(rows))
    M, rows = M[:n], rows[:n]
    # Which snapshot to draw. NOT the best one by default: correlation tracks signal
    # level, so "best correlation" silently selects a strong, clean moment. The median
    # is representative; the title says which was used and where it sits.
    order = np.argsort(rows[:, 3])
    if str(a.rec).lstrip("-").isdigit():
        a.rec, pick = int(a.rec), "chosen"
    else:
        pick = str(a.rec).lower()
        a.rec = int({"best": order[-1], "worst": order[0]}.get(pick, order[n // 2]))
    a.rec = min(max(a.rec, 0), n - 1)
    src_tti, corr = int(rows[a.rec, 1]), rows[a.rec, 3]
    pctile = 100.0 * (rows[:, 3] < corr).mean()


    R = np.loadtxt(f"{a.chan_dir}/{a.stem}_real.txt")
    I = np.loadtxt(f"{a.chan_dir}/{a.stem}_imag.txt")
    S = (R + 1j * I).reshape(-1, 4, 4, 64)

    # Source taps -> the same RB grid the measurement lives on.
    # The used subcarriers are centred on DC, so they WRAP around the FFT: the
    # receiver reads RB k at bin (first_carrier_offset + 12k) % N, not at 12k.
    # See csi_rx.c:351. Sampling at 12k instead compares against the wrong
    # frequencies entirely (magnitude-shape correlation -0.18 vs +0.85).
    N_FFT = 2048                       # 106 PRB at 30 kHz SCS
    fco = N_FFT - (106 * 12) // 2      # first_carrier_offset = 1412
    bins = [(fco + 12 * rb) % N_FFT for rb in range(nsc)]
    Sf = np.fft.fft(S, N_FFT, axis=-1)[..., bins]

    # Put the measurement on the source's scale. The dump is in the receiver's
    # own fixed-point CSI units, ~54 dB above the file, so ONE scale per
    # snapshot is needed before any level can be compared.
    #
    # Two ways to fit it, and they differ by a real amount:
    #   taps -- |al| from export_aligned (summary col 5), a least-squares fit
    #           over all 64 taps.  Taps past the channel's support carry only
    #           measurement noise, which inflates the denominator and biases
    #           the gain LOW by ~0.8 dB.  That bias is an artefact of the fit,
    #           not a level error in the replay.
    #   band -- fit on in-band energy alone, which is what this figure plots.
    #           Residual level error then measures 0.00 dB (sd 0.02 dB).
    # Default is 'band' so panel 4 shows genuine SHAPE error, not fit bias.
    if a.gain == "taps":
        g = rows[:, 5]
    else:
        num = (np.abs(Sf[rows[:, 1].astype(int)]) ** 2).sum(axis=(1, 2, 3)) ** .5
        den = (np.abs(M) ** 2).sum(axis=(1, 2, 3)) ** .5 + 1e-30
        g = num / den
    M = M * g[:, None, None, None]

    f = (np.arange(nsc) - (nsc - 1) / 2) * RB_HZ / 1e6
    C = plt.cm.viridis(np.linspace(0.05, 0.85, max(nrx, ntx)))

    fig, ax = plt.subplots(2, 2, figsize=(13, 8.5))
    fig.suptitle(f"{label}: measured vs source, in frequency  |  snapshot {a.rec} "
                 f"→ source TTI {src_tti} ({pick}: corr {corr:.3f}, "
                 f"{pctile:.0f}th pct of {n})  |  "
                 f"rx = {RXN} antennas, tx = {TXN} ports  |  solid = source, dashed = measured",
                 fontsize=11)

    # --- 1. magnitude per rx antenna.
    # ONE reference for the whole snapshot, not one per trace: export_aligned
    # fits a single complex scale per snapshot (al, summed over all rx/tx/tap),
    # so the level differences BETWEEN antennas survive alignment and are real
    # channel structure.  Normalising each trace to its own peak would erase
    # exactly that -- the rx0 > rx1 > rx2 > rx3 spread.
    ref = np.abs(Sf[src_tti]).max()
    for r in range(nrx):
        s = 20*np.log10(np.abs(Sf[src_tti, r, a.tx])/ref + 1e-12)
        m = 20*np.log10(np.abs(M[a.rec, r, a.tx])/ref + 1e-12)
        ax[0, 0].plot(f, s, color=C[r], lw=1.6, label=f"{RXN} rx{r}")
        ax[0, 0].plot(f, m, color=C[r], lw=1.4, ls="--", alpha=.65)
    ax[0, 0].set(title="Magnitude — solid = ground truth, dashed = measured\nONE scale for the whole snapshot: the gaps between antennas are real",
                 xlabel="frequency offset [MHz]", ylabel="|H(f)| [dB rel. snapshot peak]")
    both_legends(ax[0, 0], src_tti); ax[0, 0].grid(alpha=.3)

    # --- 2. phase with the bulk-delay ramp removed from both
    for r in range(nrx):
        ax[0, 1].plot(f, detrend_phase(Sf[src_tti, r, a.tx], f), color=C[r], lw=1.6, label=f"{RXN} rx{r}")
        ax[0, 1].plot(f, detrend_phase(M[a.rec, r, a.tx], f), color=C[r], lw=1.4, ls="--", alpha=.65)
    ax[0, 1].set(title="Phase — solid = ground truth, dashed = measured\nbulk-delay ramp removed from both; the residual is what carries information",
                 xlabel="frequency offset [MHz]", ylabel="residual phase [deg]")
    both_legends(ax[0, 1], src_tti); ax[0, 1].grid(alpha=.3)

    # --- 3. every transmit port into one receive antenna
    for t in range(ntx):
        s = 20*np.log10(np.abs(Sf[src_tti, a.rx, t])/ref + 1e-12)
        m = 20*np.log10(np.abs(M[a.rec, a.rx, t])/ref + 1e-12)
        ax[1, 0].plot(f, s, color=C[t], lw=1.6, label=f"{TXN} tx{t}")
        ax[1, 0].plot(f, m, color=C[t], lw=1.4, ls="--", alpha=.65)
    ax[1, 0].set(title=f"All {TXN} transmit ports into {RXN} rx{a.rx}\nsame snapshot-wide scale, so port levels are comparable",
                 xlabel="frequency offset [MHz]", ylabel="|H(f)| [dB rel. snapshot peak]")
    both_legends(ax[1, 0], src_tti); ax[1, 0].grid(alpha=.3)

    # --- 4. how big the error is, across every snapshot and antenna pair
    err = []
    for i in range(n):
        t_i = int(rows[i, 1])
        r_i = np.abs(Sf[t_i]).max()           # snapshot-wide, as in panels 1 and 3
        s = np.abs(Sf[t_i]) / r_i
        m = np.abs(M[i]) / r_i
        err.append((20*np.log10(m + 1e-12) - 20*np.log10(s + 1e-12)).reshape(-1, nsc))
    err = np.concatenate(err)
    ax[1, 1].fill_between(f, np.percentile(err, 5, axis=0), np.percentile(err, 95, axis=0),
                          color=C[1], alpha=.25, label="5–95%")
    ax[1, 1].plot(f, np.median(err, axis=0), color=C[0], lw=1.8, label="median")
    ax[1, 1].axhline(0, color="grey", ls=":", lw=1)
    ax[1, 1].set(title=f"Measured − source, all {n} snapshots × {nrx*ntx} pairs\n"
                       f"flat and centred on zero = no systematic bias",
                 xlabel="frequency offset [MHz]", ylabel="error [dB]")
    ax[1, 1].legend(fontsize=8); ax[1, 1].grid(alpha=.3)

    # Provenance box: exactly which rows of the channel file the solid curves
    # came from, so the ground truth can be checked independently.
    lines = [f"GROUND TRUTH: {a.stem}_{{real,imag}}.txt",
             f"source TTI {src_tti}  ->  file lines {src_tti*4+1}-{src_tti*4+4}",
             f"tx{a.tx} block = columns {a.tx*64+1}-{a.tx*64+64} of each line"]
    for r in range(nrx):
        h = S[src_tti, r, a.tx]
        k = int(np.argmax(np.abs(h)))
        lines.append(f"  rx{r} (line {src_tti*4+r+1}): peak tap {k}, "
                     f"{h[k].real:+.4e}{h[k].imag:+.4e}j")
    fig.text(0.012, 0.012, "\n".join(lines), fontsize=6.4, family="monospace",
             va="bottom", ha="left", color="0.35")
    fig.tight_layout(rect=[0, 0.085, 1, 1])
    fig.savefig(a.out, dpi=140)
    print(f"wrote {a.out}")

    # Full tap dump for the plotted snapshot, for independent checking.
    tp = a.out.replace(".png", "_groundtruth_taps.txt")
    with open(tp, "w") as fh:
        fh.write(f"# ground truth taps behind {os.path.basename(a.out)}\n")
        fh.write(f"# file {a.stem}_{{real,imag}}.txt, source TTI {src_tti}, "
                 f"lines {src_tti*4+1}-{src_tti*4+4}\n")
        fh.write(f"# every rx and tx at this TTI; tap spacing 16.28 ns = 4.88 m\n")
        fh.write("rx tx tap real imag abs\n")
        for r in range(4):
            for t in range(4):
                for k in range(64):
                    h = S[src_tti, r, t, k]
                    fh.write(f"{r} {t} {k} {h.real:+.9e} {h.imag:+.9e} {abs(h):.9e}\n")
    print(f"wrote {tp}")
    print(f"  snapshot {a.rec} -> source TTI {src_tti}, correlation {corr:.3f}")
    print(f"  magnitude error over the band: median {np.median(err):+.2f} dB, "
          f"IQR {np.percentile(err,75)-np.percentile(err,25):.2f} dB")


if __name__ == "__main__":
    main()
