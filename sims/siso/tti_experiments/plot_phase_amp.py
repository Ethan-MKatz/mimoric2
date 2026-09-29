#!/usr/bin/env python3
"""Plot amplitude and phase of the measured vs source channel.

Reads plot/ue1_64/aligned_H.txt (written by export_aligned.py).

Two things to know about the time axis:

  * The 21 CSI snapshots arrived ~100 s apart in wall-clock, but the tap file
    loops every 800 TTIs (0.8 s).  So they are 21 scattered samples of the
    channel's own 800-TTI trajectory, not a contiguous recording.  We plot
    against src_tti -- the position in the trajectory each snapshot matched.

  * Each snapshot was gain-aligned to the source independently, with its own
    complex scale.  Absolute phase is therefore NOT comparable between
    snapshots.  Only phase RELATIVE to rx0 within a snapshot is meaningful --
    which is exactly what the array metrics use.
"""
import argparse
import re
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def both_legends(ax, ncol=4, title=None, loc_colour="upper right", loc_style="lower left",
                 markers=("o", "s"), style_note=None):
    """Two legends on one axis. ax.legend() REPLACES the previous one, so the
    colour legend is captured and re-added before the style legend is created.

    `markers` must match what the panel actually draws -- pass ("", "") on a
    panel plotted without markers, so the style key is not a lie about the
    lines above it.  `style_note` appends a per-panel qualifier."""
    from matplotlib.lines import Line2D
    colour = ax.legend(fontsize=7.5, ncol=ncol, loc=loc_colour, framealpha=.9,
                       title=title, title_fontsize=7.5)
    ax.add_artist(colour)
    m0, m1 = markers
    h = [Line2D([], [], color="0.25", lw=1.8, ls="-", marker=m0, ms=3.5),
         Line2D([], [], color="0.25", lw=1.5, ls="--", marker=m1, ms=3, alpha=.55)]
    ax.legend(h, ["GROUND TRUTH  (channel file)", "MEASURED  (after replay)"],
              fontsize=7.5, loc=loc_style, framealpha=.9,
              title=style_note, title_fontsize=7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="plot/ue1_64/aligned_H.txt")
    ap.add_argument("--tap", type=int, default=None, help="default: strongest tap")
    ap.add_argument("--tx", type=int, default=0, help="tx port to plot")
    ap.add_argument("--out", default="plot/ue1_64/phase_amplitude.png")
    ap.add_argument("--csv", default="plot/ue1_64/phase_amp_series.txt")
    ap.add_argument("--stem", default="signal_concrete_4x4_blocker",
                    help="channel file stem, for the provenance footer")
    ap.add_argument("--label", default="DOWNLINK CSI-RS (rx = UE ant, tx = gNB port)", help="direction/signal shown in the title")
    a = ap.parse_args()

    D = np.loadtxt(a.data)
    nrec = int(D[:, 0].max()) + 1
    src = (D[:, 5] + 1j * D[:, 6]).reshape(nrec, 4, 4, 64)
    twn = (D[:, 7] + 1j * D[:, 8]).reshape(nrec, 4, 4, 64)
    tti = D[:, 1].reshape(nrec, 4, 4, 64)[:, 0, 0, 0].astype(int)

    m = re.search(r"rx\s*=\s*([^,)]+)", a.label)
    rxname = m.group(1).strip() if m else "rx antenna"

    tap = a.tap if a.tap is not None else int(np.argmax((np.abs(src) ** 2).mean(axis=(0, 1, 2))))
    o = np.argsort(tti)                      # order by position in the trajectory
    t, S, T = tti[o], src[o, :, a.tx, tap], twn[o, :, a.tx, tap]   # [rec, rx]

    # phase relative to rx0 -- the only cross-snapshot-comparable phase
    pS = np.unwrap(np.angle(S * np.conj(S[:, :1])), axis=1)
    pT = np.unwrap(np.angle(T * np.conj(T[:, :1])), axis=1)

    fig, ax = plt.subplots(2, 2, figsize=(13, 8.5))
    fig.suptitle(f"{a.label}: measured twin vs source  |  tap {tap}, tx port {a.tx}  |  "
                 f"{nrec} snapshots over an 800-TTI trajectory", fontsize=12)
    C = plt.cm.viridis(np.linspace(0.05, 0.85, 4))

    drawn_amp_src, drawn_amp_twn = [], []
    for r in range(4):
        drawn_amp_src += ax[0, 0].plot(t, 20 * np.log10(np.abs(S[:, r]) + 1e-30), "-o", ms=3.5, color=C[r], label=f"rx{r}")
        drawn_amp_twn += ax[0, 0].plot(t, 20 * np.log10(np.abs(T[:, r]) + 1e-30), "--s", ms=3, color=C[r], alpha=.55)
    ax[0, 0].set(title="Amplitude vs trajectory position\nsolid = ground truth, dashed = measured",
                 xlabel="source TTI", ylabel="|H| [dB]")
    both_legends(ax[0, 0], ncol=4, title=f"colour = {rxname}\n{len(t)} snapshots of 800 TTIs",
                 style_note=f"one point per snapshot, tap {tap}, tx port {a.tx}")
    ax[0, 0].grid(alpha=.3)

    drawn_ph_src, drawn_ph_twn = [None], [None]      # index by rx; rx0 is the reference
    for r in range(1, 4):
        drawn_ph_src += ax[0, 1].plot(t, np.degrees(pS[:, r]), "-o", ms=3.5, color=C[r], label=f"rx{r}-rx0")
        drawn_ph_twn += ax[0, 1].plot(t, np.degrees(pT[:, r]), "--s", ms=3, color=C[r], alpha=.55)
    ax[0, 1].set(title="Phase relative to rx0\nabsolute phase is not comparable across snapshots",
                 xlabel="source TTI", ylabel="phase [deg]")
    both_legends(ax[0, 1], ncol=3, title=f"colour = {rxname}, phase vs rx0\n{len(t)} snapshots of 800 TTIs",
                 style_note=f"one point per snapshot, tap {tap}, tx port {a.tx}")
    ax[0, 1].grid(alpha=.3)

    idx = np.linspace(0, len(t) - 1, 4).astype(int)
    for j, i in enumerate(idx):
        ax[1, 0].plot(range(4), np.degrees(pS[i]), "-o", ms=4, color=C[j], label=f"TTI {t[i]}")
        ax[1, 0].plot(range(4), np.degrees(pT[i]), "--s", ms=3.5, color=C[j], alpha=.55)
    ax[1, 0].set(title="Phase ramp across the array\nstraight line = real array geometry",
                 xlabel="rx element index", ylabel="phase rel. rx0 [deg]")
    both_legends(ax[1, 0], ncol=2, title="colour = source TTI (of 800)")
    ax[1, 0].grid(alpha=.3)

    eS = (np.abs(src[:, :, a.tx, :]) ** 2).mean(axis=(0, 1))
    eT = (np.abs(twn[:, :, a.tx, :]) ** 2).mean(axis=(0, 1))
    ax[1, 1].plot(10 * np.log10(eS / eS.max() + 1e-20), "-", lw=1.8, color="0.25")
    ax[1, 1].plot(10 * np.log10(eT / eT.max() + 1e-20), "--", lw=1.8, color="0.25", alpha=.55)
    ax[1, 1].axvline(tap, color="crimson", ls=":", lw=1.2, label=f"aligned tap {tap}")
    ax[1, 1].set(title="Tap energy profile\nprecursors below tap 6 are absent in the measurement",
                 xlabel="tap index", ylabel="energy [dB]")
    both_legends(ax[1, 1], ncol=1, markers=("", ""),
                 title=f"averaged over 4 {rxname} x {len(t)} snapshots",
                 style_note=f"tx port {a.tx}; each curve normalised to its own peak")
    ax[1, 1].grid(alpha=.3)

    # Provenance footer: every TTI on this figure, and where it lives in the
    # channel file, so any curve can be checked against the source by hand.
    nuniq = len(set(t.tolist()))
    def lines(x):
        return f"{x} (lines {x*4+1}-{x*4+4})"
    foot = [f"GROUND TRUTH: {a.stem}_{{real,imag}}.txt     line = TTI*4 + rx + 1     col = tx*64 + tap + 1",
            f"panels 1-2 (top):     x-axis IS the source TTI -- {len(t)} snapshots spanning TTI "
            f"{t.min()}..{t.max()} of 800, at {nuniq} distinct position" + ("s" if nuniq != 1 else "")]
    if nuniq < len(t):
        u, c = np.unique(t, return_counts=True)
        foot.append("                      positions sampled: "
                    + ",  ".join(f"TTI {int(x)} x{int(n)}" for x, n in zip(u, c)))
    foot.append("panel 3 (phase ramp): " + ",  ".join(lines(int(t[i])) for i in idx))
    foot.append(f"panel 4 (tap prof.):  mean over all {len(t)} snapshots, tap {tap}, tx port {a.tx}")
    fig.tight_layout(rect=[0, 0.075, 1, 1])
    fig.text(0.008, 0.005, "\n".join(foot), fontsize=7, family="monospace", va="bottom")
    fig.savefig(a.out, dpi=140)
    print(f"wrote {a.out}")

    # Read the numbers back OUT of the drawn lines, not from the arrays above.
    # If the plotting call and the table ever disagree, this file follows the
    # figure -- so an independent check against it is checking what you see.
    with open(a.csv, "w") as f:
        f.write(f"# tap {tap}, tx {a.tx}; phase columns are relative to rx0, in degrees\n")
        f.write("# values read back from the plotted Line2D artists (panels 1 and 2)\n")
        f.write("src_tti rx src_amp_dB twin_amp_dB src_phase_deg twin_phase_deg\n")
        xs = drawn_amp_src[0].get_xdata()
        for i in range(len(xs)):
            for r in range(4):
                aS = drawn_amp_src[r].get_ydata()[i]
                aT = drawn_amp_twn[r].get_ydata()[i]
                if r == 0:
                    qS = qT = 0.0
                else:
                    qS = drawn_ph_src[r].get_ydata()[i]
                    qT = drawn_ph_twn[r].get_ydata()[i]
                f.write(f"{int(xs[i])} {r} {aS:.4f} {aT:.4f} {qS:.3f} {qT:.3f}\n")
    print(f"wrote {a.csv}")


if __name__ == "__main__":
    main()
