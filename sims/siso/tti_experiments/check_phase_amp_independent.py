#!/usr/bin/env python3
"""Independent check of phase_amplitude.png against the raw replay dump.

Shares NO code with the plotting pipeline (no csi_to_npy, no export_aligned,
no aligned_H.txt).  It re-derives everything from two sources:

    raw dump      dl_csi_ue1.txt / ul_srs_gnb.txt   -- what the receiver measured
    channel file  signal_concrete_4x4_blocker_{real,imag}   -- ground truth

and compares only GAIN-FREE quantities, so no gain fit is involved:

    amplitude of rx r relative to rx0   [dB]
    phase     of rx r relative to rx0   [deg]

Both are computed in FREQUENCY (averaged over all RBs), so the tap-grid and
truncation problems in aligned_H.txt cannot touch this check.

It also does its OWN source-TTI search rather than trusting align_summary.txt.
Finally it compares all of that with what the plot actually drew
(phase_amp_series.txt), giving a three-way check: truth vs replay vs plot.

    python3 check_phase_amp_independent.py            # downlink
    python3 check_phase_amp_independent.py --ul       # uplink
"""
import argparse
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--ul", action="store_true")
ap.add_argument("--dir", default="plot/ue1_64")
ap.add_argument("--chan", default="/home/wayslab/tinytwin-oai/channel/signal_concrete_4x4_blocker")
ap.add_argument("--tx", type=int, default=0)
a = ap.parse_args()

# ---- 1. raw dump, parsed here from scratch ------------------------------
dump = f"{a.dir}/{'ul_srs_gnb' if a.ul else 'dl_csi_ue1'}.txt"
M = []
for line in open(dump):
    f = line.split()
    nrx, ntx, nsc = int(f[4]), int(f[5]), int(f[6])
    v = np.array(f[7:], dtype=float)
    M.append((v[0::2] + 1j * v[1::2]).reshape(nrx, ntx, nsc))   # [rx][tx][RB]
M = np.array(M)

# ---- 2. ground truth, sampled at the SAME RB frequencies ----------------
S = (np.loadtxt(a.chan + "_real.txt") + 1j * np.loadtxt(a.chan + "_imag.txt")).reshape(-1, 4, 4, 64)
N = 2048
fco = N - (106 * 12) // 2                      # first_carrier_offset
bins = [(fco + 12 * k) % N for k in range(nsc)]
Sf = np.fft.fft(S, N, axis=-1)[..., bins]      # [tti][rx][tx][RB]

# ---- 3. own TTI search, insensitive to timing offset --------------------
# Per-RB spatial correlation, magnitude taken per RB: a common phase per RB
# (receiver timing / CFO) cannot affect it.
def score(m, s):
    num = np.abs((m * np.conj(s)).sum(axis=(0, 1))).sum()
    return num / (np.linalg.norm(m) * np.linalg.norm(s) + 1e-30)

tti = np.array([int(np.argmax([score(m, s) for s in Sf])) for m in M])

# ---- 4. gain-free quantities, in frequency ------------------------------
def rel(H):                                    # H: [rx][RB] for one tx
    amp = 10 * np.log10((np.abs(H) ** 2).mean(-1) / (np.abs(H[0]) ** 2).mean())
    ph = np.degrees(np.angle((H * np.conj(H[0])).sum(-1)))
    return amp, ph

wrap = lambda d: (d + 180) % 360 - 180

# ---- 5. what the plot drew -----------------------------------------------
# Robust to header/comment lines being added upstream: keep only numeric rows.
_sp = f"{a.dir}/phase_amp{'_ul' if a.ul else ''}_series.txt"
_rows = []
for _ln in open(_sp):
    if _ln.startswith("#"):
        continue
    try:
        _rows.append([float(x) for x in _ln.split()])
    except ValueError:
        continue                    # the column-name line
ser = np.array(_rows)
# cols: src_tti rx src_amp_dB twin_amp_dB src_phase_deg twin_phase_deg

print(f"{'UL' if a.ul else 'DL'}  {dump}  {len(M)} records, tx port {a.tx}\n")
print("rec  own_tti  plot_tti | rx | amp rel rx0 [dB]: truth  replay  plot | "
      "phase rel rx0 [deg]: truth  replay  plot")
e_rt_a, e_rt_p, e_rp_a, e_rp_p, tti_agree = [], [], [], [], 0
used = set()
for i, m in enumerate(M):
    at, pt = rel(Sf[tti[i], :, a.tx])
    am, pm = rel(m[:, a.tx])
    rows = ser[ser[:, 0] == tti[i]]
    has_plot = len(rows) >= 4 and tti[i] not in used
    if has_plot:
        tti_agree += 1
        used.add(tti[i])
        r0 = rows[rows[:, 1] == 0][0]
    for r in range(1, 4):
        e_rt_a.append(am[r] - at[r]); e_rt_p.append(wrap(pm[r] - pt[r]))
        if has_plot:
            rr = rows[rows[:, 1] == r][0]
            pa = rr[3] - r0[3]                  # plotted twin amp rel rx0
            pp = wrap(rr[5])                    # plotted twin phase rel rx0
            e_rp_a.append(am[r] - pa); e_rp_p.append(wrap(pm[r] - pp))
            plot_s = f"{pa:+6.2f}"; plotp_s = f"{pp:+7.1f}"
        else:
            plot_s = "   -  "; plotp_s = "    -  "
        if i < 6:
            print(f"{i:3d}  {tti[i]:6d}  {'yes' if has_plot else ' - ':>7} | {r}  | "
                  f"{at[r]:+6.2f} {am[r]:+6.2f} {plot_s} | "
                  f"{pt[r]:+7.1f} {pm[r]:+7.1f} {plotp_s}")
print("  ... (first 6 records shown)\n")

def stat(x):
    x = np.abs(np.array(x)); return f"median {np.median(x):5.2f}   p95 {np.percentile(x, 95):5.2f}   max {x.max():5.2f}"

print("REPLAY vs TRUTH   (is the replay faithful?)")
print(f"  amp   error [dB] : {stat(e_rt_a)}")
print(f"  phase error [deg]: {stat(e_rt_p)}")
if e_rp_a:
    print("REPLAY vs PLOT    (does the plot show the replay faithfully?)")
    print(f"  amp   error [dB] : {stat(e_rp_a)}")
    print(f"  phase error [deg]: {stat(e_rp_p)}")
