#!/usr/bin/env python3
"""Convert the UE's complex CSI-RS dump into [n_tti, rx, tx, taps] for validate_mimo.py.

The UE logs the frequency-domain estimate H[rx][tx][subcarrier] on the CSI-RS
sample grid.  validate_mimo.py wants taps (it FFTs the last axis itself to get
H(f)), so we IFFT across subcarriers here.  The CSI-RS grid is one sample per
RB -- and per *other* RB when freq_density<=1 -- so the tap axis it yields is a
coarse, aliased version of the generator's 64-tap impulse response.  That is
fine for the metrics that matter: phase ramp, direction cosine, rx correlation,
singular values and MRC gain all read the spatial structure, not tap detail.

Usage:  ./csi_to_npy.py logs/dl_csi_ue1.txt -o twin_measured.npy [--taps 64]
"""
import argparse, sys
import numpy as np


def load(path):
    recs, meta = [], None
    with open(path) as f:
        for ln, line in enumerate(f, 1):
            w = line.split()
            if not w or w[0] not in ("CSI", "SRS"):   # DL CSI-RS or UL SRS dump
                continue
            try:
                _, idx, frame, slot, nrx, ntx, nsc = w[:7]
                nrx, ntx, nsc = int(nrx), int(ntx), int(nsc)
                vals = np.array(w[7:], dtype=np.float64)
            except ValueError:
                print(f"  skipping malformed line {ln}", file=sys.stderr)
                continue
            need = nrx * ntx * nsc * 2
            if vals.size != need:
                print(f"  skipping line {ln}: {vals.size} values, expected {need}", file=sys.stderr)
                continue
            if meta is None:
                meta = (nrx, ntx, nsc)
            elif meta != (nrx, ntx, nsc):
                print(f"  skipping line {ln}: shape {(nrx,ntx,nsc)} != {meta}", file=sys.stderr)
                continue
            H = (vals[0::2] + 1j * vals[1::2]).reshape(nrx, ntx, nsc)
            recs.append(H)
    if not recs:
        sys.exit(f"{path}: no usable CSI records")
    return np.stack(recs), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("-o", "--out", default="twin_measured.npy")
    ap.add_argument("--taps", type=int, default=None,
                    help="truncate/zero-pad the tap axis to this length (e.g. 64 to match the source)")
    a = ap.parse_args()

    Hf, (nrx, ntx, nsc) = load(a.dump)
    print(f"{a.dump}: {Hf.shape[0]} records, {nrx} rx x {ntx} tx, {nsc} subcarriers")

    # subcarriers -> taps.  Non-uniform CSI-RS spacing is uniform *within* the
    # kept grid, so a plain IFFT is the right inverse for that grid.
    Ht = np.fft.ifft(Hf, axis=-1)
    if a.taps:
        if a.taps <= Ht.shape[-1]:
            Ht = Ht[..., :a.taps]
        else:
            Ht = np.concatenate(
                [Ht, np.zeros(Ht.shape[:-1] + (a.taps - Ht.shape[-1],), complex)], axis=-1)
    np.save(a.out, Ht)
    e = np.abs(Ht) ** 2
    print(f"wrote {a.out}  shape {Ht.shape}  dominant tap {int(np.argmax(e.mean(axis=(0,1,2))))}")
    print(f"  per-rx mean power (dB): "
          + "  ".join(f"rx{r} {10*np.log10(e[:,r].mean()+1e-30):.2f}" for r in range(nrx)))


if __name__ == "__main__":
    main()
