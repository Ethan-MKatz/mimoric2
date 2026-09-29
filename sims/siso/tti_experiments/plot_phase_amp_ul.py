#!/usr/bin/env python3
"""Uplink phase/amplitude plot, from the gNB's SRS channel matrix (4x4).

Why SRS and not DMRS
--------------------
PUSCH DMRS is per *layer*, and uplink rank here is 1, so a DMRS estimate is
H[rx] -- a 4x1 vector.  SRS is sounded per UE antenna port, so the gNB's
codebook-usage SRS report carries the full H[gNB antenna][UE port][PRG]: the
only 4x4 uplink matrix in the stack.

Where the data comes from
-------------------------
gNB_scheduler_ulsch.c dumps that matrix to ul_srs_gnb.txt (TT_UL_SRS_LOG), in
the same text format as the UE's dl_csi_ue1.txt, laid out [rx][tx][sc] with
rx = gNB antenna and tx = UE port.  That is deliberate: it lets this script run
the exact pipeline the downlink uses, rather than a second implementation.

    ul_srs_gnb.txt -> csi_to_npy -> export_aligned (--tag _ul) -> plot_phase_amp

Outputs, beside the downlink ones and never overwriting them:
    twin_measured_ul.npy  aligned_H_ul.txt  align_summary_ul.txt  tap_profile_ul.txt
    phase_amp_ul_series.txt  phase_amplitude_ul.png

Caveat: the uplink replay at the gNB reads the tap file with its own cursor,
independent of the UE's downlink cursor, so UL and DL sit at different points
of the 800-TTI trajectory.  Alignment searches all 800 TTIs, so this does not
affect the score -- but UL and DL snapshots are not simultaneous.
"""
import argparse, os, subprocess, sys

REPO = "/home/wayslab/tinytwin-oai"
HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    print("[ul] " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"[ul] step failed ({r.returncode}): {cmd[1]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="plot/ue1_64")
    ap.add_argument("--dump", default=None, help="default: <dir>/ul_srs_gnb.txt, else logs/")
    ap.add_argument("--stem", default="signal_concrete_4x4_blocker")
    ap.add_argument("--tx", type=int, default=0, help="UE SRS port to plot")
    a = ap.parse_args()

    dump = a.dump
    if dump is None:
        for c in (os.path.join(a.dir, "ul_srs_gnb.txt"), f"{REPO}/logs/ul_srs_gnb.txt"):
            if os.path.exists(c) and os.path.getsize(c) > 0:
                dump = c
                break
    if not dump:
        sys.exit("[ul] no SRS dump with data -- check the gNB log for 'TT-SRS' and "
                 "'[UL SRS dump]'. If TT-SRS never appears, SRS reports are not reaching MAC.")

    npy = os.path.join(a.dir, "twin_measured_ul.npy")
    py = sys.executable
    run([py, f"{HERE}/csi_to_npy.py", dump, "-o", npy, "--taps", "64"])
    run([py, f"{HERE}/export_aligned.py", "--npy", npy, "--stem", a.stem,
         "--outdir", a.dir, "--tag", "_ul"])
    run([py, f"{HERE}/plot_phase_amp.py",
         "--data", os.path.join(a.dir, "aligned_H_ul.txt"),
         "--out", os.path.join(a.dir, "phase_amplitude_ul.png"),
         "--csv", os.path.join(a.dir, "phase_amp_ul_series.txt"),
         "--tx", str(a.tx),
         "--label", "UPLINK SRS (rx = gNB ant, tx = UE port)"])
    run([py, f"{HERE}/align_twin.py", "--npy", npy, "--stem", a.stem])


if __name__ == "__main__":
    main()
