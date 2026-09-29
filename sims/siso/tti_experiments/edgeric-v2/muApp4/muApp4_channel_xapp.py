#!/usr/bin/env python3
"""muApp4 - a minimal xApp that consumes a per-antenna channel from the RAN.

Two sources, selected with --mode:

  dl  (default)  the UE's CSI-RS estimate, published from nr-uesoftmodem.
                 THIS IS YOUR REPLAYED CHANNEL - the downlink carries
                 signal_concrete_4x4.  Raw framing, 4x4x106 complex.

  ul             the gNB's MIMO-RIC export (PUSCH DMRS) over protobuf.
                 Uplink, so with --ULCHAN off it is NOT your replayed
                 channel - useful to prove the transport, not the twin.


Subscribes to the gNB's RT-E2 report stream, pulls UeMetrics.ul_channel out of
each message, and computes per-antenna statistics live.  This is the smallest
thing that proves the ZMQ path carries a usable per-antenna channel.

What it derives, per report:
  * per-rx power in dB          - is every antenna alive?
  * rx0-relative phase          - is there spatial structure, or one antenna copied?
  * rx covariance condition no. - how many spatial modes the channel supports

Run inside the edgeric container (it reaches the gNB at 192.168.70.140), or on
the host if that address is routable:

    python3 muApp4_channel_xapp.py            # live table
    python3 muApp4_channel_xapp.py --csv out.txt
"""
import argparse, os, sys, time
import numpy as np
import zmq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import metrics_pb2


def unpack(ue):
    """UeMetrics.ul_channel -> complex [nrx, nsc], or None if absent/malformed."""
    nrx, nsc = ue.ul_channel_nrx, ue.ul_channel_nsc
    if nrx == 0 or nsc == 0:
        return None
    v = np.asarray(ue.ul_channel, dtype=np.float64)
    if v.size < nrx * nsc * 2:
        return None
    v = v[: nrx * nsc * 2]
    return (v[0::2] + 1j * v[1::2]).reshape(nrx, nsc)


DL_MAGIC = 0x54544358   # "TTCX"


def recv_dl(sub):
    """Two-part message: 7 uint32 header, then nrx*ntx*nsc*2 float32."""
    hdr = np.frombuffer(sub.recv(), dtype=np.uint32)
    body = np.frombuffer(sub.recv(), dtype=np.float32)
    if hdr.size < 7 or hdr[0] != DL_MAGIC:
        return None
    seq, frame, slot, nrx, ntx, nsc = (int(x) for x in hdr[1:7])
    need = nrx * ntx * nsc * 2
    if body.size < need:
        return None
    v = body[:need].astype(np.float64)
    H = (v[0::2] + 1j * v[1::2]).reshape(nrx, ntx, nsc)
    return seq, frame, slot, H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dl", "ul"], default="dl")
    ap.add_argument("--addr", default=None,
                    help="default: dl -> tcp://192.168.70.151:5558, ul -> tcp://192.168.70.140:5555")
    ap.add_argument("--csv", help="also append rows to this file")
    ap.add_argument("--every", type=int, default=1, help="print every Nth report")
    a = ap.parse_args()

    if a.addr is None:
        a.addr = ("tcp://192.168.70.151:5558" if a.mode == "dl"
                  else "tcp://192.168.70.140:5555")
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    # CONFLATE keeps only the newest message, but it cannot be used with the
    # multipart DL framing -- so bound the queue instead.
    if a.mode == "ul":
        sub.setsockopt(zmq.CONFLATE, 1)
    else:
        sub.setsockopt(zmq.RCVHWM, 8)
    sub.connect(a.addr)
    src = "DOWNLINK CSI-RS (your replayed channel)" if a.mode == "dl" \
          else "UPLINK PUSCH DMRS (not the replayed channel)"
    print(f"muApp4: subscribed to {a.addr}\n        source: {src}", flush=True)

    out = open(a.csv, "w", buffering=1) if a.csv else None
    if out:
        out.write("# wallclock tti rnti nrx nsc pow_rx0..N_dB phase_rx1..N_deg cond_dB\n")

    seen = with_chan = 0
    print(f"\n{'tti':>8} {'rnti':>6} {'nrx':>4} {'nsc':>4} | "
          f"{'per-rx power dB':^30} | {'phase vs rx0 deg':^24} | {'cond dB':>8}")
    print("-" * 96)

    while True:
        if a.mode == "dl":
            got = recv_dl(sub)
            if got is None:
                continue
            seq, frame, slot, H4 = got
            seen += 1
            # collapse the tx axis for the summary table: total power per rx
            reports = [(frame * 100 + slot, 0, H4.reshape(H4.shape[0], -1))]
        else:
            m = metrics_pb2.Metrics()
            m.ParseFromString(sub.recv())
            seen += 1
            reports = [(m.tti_cnt, ue.rnti, unpack(ue)) for ue in m.ue_metrics]

        for tti, rnti, H in reports:
            if H is None:
                continue
            with_chan += 1
            if with_chan % a.every:
                continue

            pw = 10 * np.log10((np.abs(H) ** 2).mean(axis=1) + 1e-30)   # [nrx]

            # Spatial signature from the rx covariance, NOT a mean over columns.
            # Averaging H across subcarriers cancels: the phase rotates with
            # frequency, so the mean tends to zero and the angle is noise. The
            # principal eigenvector of R is the phase reference that survives -
            # the same quantity the offline validator uses.
            R = H @ H.conj().T                                           # [nrx, nrx]
            ev, evec = np.linalg.eigh(R)
            sig = evec[:, -1]                                            # dominant mode
            ph = np.degrees(np.angle(sig * np.conj(sig[0])))
            ev = ev[::-1]
            cond = 10 * np.log10((ev[0] + 1e-30) / (ev[-1] + 1e-30))

            print(f"{tti:>8} {rnti:>6x} {H.shape[0]:>4} {H.shape[1]:>4} | "
                  + " ".join(f"{p:6.1f}" for p in pw)
                  + " | " + " ".join(f"{p:7.1f}" for p in ph[1:])
                  + f" | {cond:8.1f}", flush=True)

            if out:
                out.write(f"{time.time():.6f} {tti} {rnti} {H.shape[0]} {H.shape[1]} "
                          + " ".join(f"{p:.3f}" for p in pw) + " "
                          + " ".join(f"{p:.3f}" for p in ph[1:])
                          + f" {cond:.3f}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nmuApp4: stopped")
