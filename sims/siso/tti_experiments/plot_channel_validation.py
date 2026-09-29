#!/usr/bin/env python3
"""Validation figure for a replayed DL MIMO channel.

Reads the gNB's snr.txt (DL RANK / DL CQI / UL SNR, written as
"TTI Index: n" followed by "<NAME>: <value> RNTI: <rnti>") and overlays it on the
per-TTI power of the tap file that was actually replayed. If the replay is live,
the measured traces move with the file's power; if it is not, they sit flat.

  ./plot_channel_validation.py --stem signal_concrete_4x4_t16 --taps 16
"""
import argparse, os, re, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def parse_snr(path, wanted=("DL RANK", "DL CQI", "UL SNR")):
    """-> {metric: {rnti: (ttis, values)}}"""
    out = {m: {} for m in wanted}
    pat = re.compile(r"^(%s):\s*([-\d.]+)\s+RNTI:\s*([0-9a-fA-F]+)" % "|".join(wanted))
    tti = None
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("TTI "):
                try: tti = int(line.split(":")[1])
                except (IndexError, ValueError): tti = None
                continue
            m = pat.match(line)
            if m and tti is not None:
                name, val, rnti = m.group(1), float(m.group(2)), m.group(3)
                t, v = out[name].setdefault(rnti, ([], []))
                t.append(tti); v.append(val)
    return out

def parse_dlch(path):
    """dl_channel.txt -> (idx, [per-antenna dB arrays]). One row per SSB."""
    idx, cols = [], None
    with open(path, errors="replace") as f:
        for line in f:
            if not line.startswith("DLCH"):
                continue
            p = line.split()
            if len(p) < 3:
                continue
            n = int(p[2])
            if cols is None:
                cols = [[] for _ in range(n)]
            if len(p) < 3 + n or len(cols) != n:
                continue
            idx.append(int(p[1]))
            for a in range(n):
                cols[a].append(float(p[3 + a]))
    return np.array(idx), [np.array(c) for c in (cols or [])]


def file_power(stem, taps, ntx=4, nrx=4):
    """Per-TTI total channel power (dB) of the replayed tap file."""
    base = os.path.join(REPO, "channel", stem)
    R = [l.split() for l in open(base + "_real.txt")]
    I = [l.split() for l in open(base + "_imag.txt")]
    n = min(len(R), len(I)) // nrx
    pw = []
    for t in range(n):
        e = 0.0
        for r in range(nrx):
            row_r, row_i = R[t * nrx + r], I[t * nrx + r]
            e += sum(float(row_r[i]) ** 2 + float(row_i[i]) ** 2 for i in range(ntx * taps))
        pw.append(10 * np.log10(e) if e > 0 else -200.0)
    return np.array(pw)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snr", default=os.path.join(REPO, "logs", "snr.txt"))
    ap.add_argument("--stem", default="signal_concrete_4x4_t16")
    ap.add_argument("--taps", type=int, default=16)
    ap.add_argument("--dlch", default=os.path.join(REPO, "logs", "dl_channel.txt"))
    ap.add_argument("--ntx", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(REPO, "logs", "channel_validation.png"))
    a = ap.parse_args()

    if not os.path.exists(a.snr):
        sys.exit(f"missing {a.snr}")
    data = parse_snr(a.snr)
    ranks = data["DL RANK"]
    if not ranks:
        print("WARNING: no 'DL RANK' lines in snr.txt -- gNB needs the rank-logging build "
              "and a UE attached with DL traffic.", file=sys.stderr)

    # busiest RNTI wins (older runs leave stale ones behind)
    def busiest(d):
        return max(d.items(), key=lambda kv: len(kv[1][0]))[0] if d else None
    rnti = busiest(ranks) or busiest(data["DL CQI"]) or busiest(data["UL SNR"])

    fig, ax = plt.subplots(4, 1, figsize=(13, 11), dpi=140, sharex=False)
    fig.suptitle(f"DL MIMO channel replay validation — tap set '{a.stem}' ({a.taps} taps)"
                 + (f", RNTI {rnti}" if rnti else ""), fontsize=13)

    def draw(axis, metric, color, ylabel, step=False):
        d = data[metric].get(rnti)
        if not d or not d[0]:
            axis.text(.5, .5, f"no {metric} samples", ha="center", va="center",
                      transform=axis.transAxes, color="firebrick")
            axis.set_ylabel(ylabel); return
        t, v = np.array(d[0]), np.array(d[1])
        (axis.step if step else axis.plot)(t, v, color=color, lw=1.0,
                                           **({"where": "post"} if step else {}))
        axis.set_ylabel(ylabel); axis.grid(alpha=.3)
        axis.set_title(f"{metric}   n={len(v)}  mean={v.mean():.2f}  min={v.min():g}  max={v.max():g}",
                       fontsize=9, loc="left")

    draw(ax[0], "DL RANK", "tab:blue", "rank (layers)", step=True)
    d = data["DL RANK"].get(rnti)
    if d and d[1]:
        ax[0].set_ylim(0.5, max(2.5, max(d[1]) + .5))
    draw(ax[1], "DL CQI", "tab:green", "DL CQI")
    # measured per-rx-antenna DL power (SSB-rate, independent of user traffic)
    try:
        di, dcols = parse_dlch(a.dlch)
        if len(di) and dcols:
            for r, c in enumerate(dcols):
                ax[2].plot(di, c - dcols[0], lw=1.0, label=f"rx{r} - rx0")
            ax[2].legend(fontsize=7, ncol=4)
            spread = max(np.ptp(c - dcols[0]) for c in dcols)
            ax[2].set_title(f"MEASURED per-rx DL power rel. rx0   n={len(di)}  "
                            f"max swing={spread:.1f} dB   "
                            f"(no-replay baseline would be flat at -14/-20/-26)",
                            fontsize=9, loc="left")
        else:
            ax[2].text(.5, .5, "no DLCH rows yet", ha="center", va="center",
                       transform=ax[2].transAxes, color="firebrick")
    except FileNotFoundError:
        ax[2].text(.5, .5, f"missing {a.dlch}", ha="center", va="center",
                   transform=ax[2].transAxes, color="firebrick")
    ax[2].set_ylabel("dB rel. rx0"); ax[2].grid(alpha=.3)

    try:
        pw = file_power(a.stem, a.taps, ntx=a.ntx)
        ax[3].plot(np.arange(len(pw)), pw, color="tab:red", lw=1.0)
        ax[3].set_title(f"reference: replayed tap-file power per file-TTI "
                        f"(range {pw.max()-pw.min():.2f} dB)", fontsize=9, loc="left")
        ax[3].set_ylabel("channel power (dB)"); ax[3].set_xlabel("file TTI index")
        ax[3].grid(alpha=.3)
    except Exception as e:
        ax[3].text(.5, .5, f"tap file unreadable: {e}", ha="center", va="center",
                   transform=ax[3].transAxes, color="firebrick")

    for x in ax[:3]:
        x.set_xlabel("gNB TTI counter")
    fig.tight_layout(rect=[0, 0, 1, .97])
    fig.savefig(a.out)
    print(f"wrote {a.out}")
    for m in ("DL RANK", "DL CQI", "UL SNR"):
        dd = data[m].get(rnti)
        print(f"  {m:8s}: {len(dd[1]) if dd else 0} samples"
              + (f", mean {np.mean(dd[1]):.2f}, distinct {sorted(set(dd[1]))[:6]}" if dd and dd[1] else ""))

if __name__ == "__main__":
    main()
