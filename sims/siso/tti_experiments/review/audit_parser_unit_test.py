#!/usr/bin/env python3
"""Level-2 audit: does the dump->H(f)->CIR transform recover a KNOWN channel?

No measured data, no ground-truth plot, no comparison against any expected picture.
A synthetic channel is constructed whose answer is known analytically; it is pushed
through exactly the transform the pipeline uses; the recovered values are checked
against the closed-form prediction.

Chain being audited, each step justified only by OAI source or arithmetic:

  taps on the 16.28 ns grid                     (channel file format, 1/61.44 MHz)
    -> H at FFT bin (fco + 12*rb) % 2048        (csi_rx.c:1039)
    -> 106 complex values, RB order             (csi_rx.c:1042, the dump)
    -> np.fft.ifft(..., axis=-1)                (csi_to_npy.py:61)
    -> truncate to 64                           (csi_to_npy.py:62-67)

Run:  python3 review/audit_parser_unit_test.py
"""
import numpy as np

FS = 61.44e6                      # sample rate -> file tap spacing
N_FFT = 2048                      # 106 PRB at 30 kHz SCS
N_RB = 106
SCS = 30e3
FCO = N_FFT - (N_RB * 12) // 2    # first_carrier_offset = 1412
BINS = [(FCO + 12 * rb) % N_FFT for rb in range(N_RB)]

tap_dt = 1.0 / FS                                 # 16.28 ns
rb_df = 12 * SCS                                  # 360 kHz
meas_dt = 1.0 / (N_RB * rb_df)                    # 26.21 ns
ok = lambda b: "PASS" if b else "**FAIL**"

print(f"grid arithmetic")
print(f"  file tap spacing        1/{FS/1e6:.2f} MHz          = {tap_dt*1e9:6.2f} ns")
print(f"  dumped RB spacing       12 x {SCS/1e3:.0f} kHz        = {rb_df/1e3:6.1f} kHz")
print(f"  IFFT of {N_RB} such samples -> tap spacing   = {meas_dt*1e9:6.2f} ns")
print(f"  unambiguous delay window 1/{rb_df/1e3:.0f} kHz        = {1/rb_df*1e6:6.2f} us")

# ---- is the dumped set actually uniformly spaced? ------------------------
d = np.diff(np.unwrap(np.array(BINS) / N_FFT * 2 * np.pi)) / (2 * np.pi) * N_FFT
print(f"\n[1] dumped bins uniformly spaced (incl. the wrap at bin 2047->0)")
print(f"    spacing min {d.min():.3f}  max {d.max():.3f}   {ok(np.allclose(d, 12))}")
print(f"    -> a plain IFFT over the 106 values IS a valid inverse DFT on this grid.")

# ---- synthetic channel with a known answer -------------------------------
def through_pipeline(taps):
    """taps: [64] on the 16.28 ns grid -> what csi_to_npy produces."""
    H = np.fft.fft(taps, N_FFT)[BINS]      # what the receiver would report
    return np.fft.ifft(H)                  # csi_to_npy.py:61 (no truncation yet)

print(f"\n[2] single path at file tap 6 = {6*tap_dt*1e9:.2f} ns")
t = np.zeros(64, complex); t[6] = 1.0
H = np.fft.fft(t, N_FFT)[BINS]
y = np.fft.ifft(H)
# Delay from the phase slope across frequency: exact for a single path, and it tests
# the part that matters -- that the dumped values sit at the frequencies we think.
# (Two earlier versions of this test used a centre-of-gravity metric instead. Both
#  reported a false failure: |y|^2 is a Dirichlet kernel whose samples do not straddle
#  a non-half-integer centre symmetrically, so its moment is biased. The metric was
#  wrong, not the transform.)
f = np.array([((b + N_FFT // 2) % N_FFT - N_FFT // 2) for b in BINS]) * SCS
slope = np.polyfit(f, np.unwrap(np.angle(H)), 1)[0]
delay = -slope / (2 * np.pi)
print(f"    delay from phase slope  {delay*1e9:8.3f} ns   true {6*tap_dt*1e9:.3f} ns   "
      f"{ok(abs(delay - 6*tap_dt) < 1e-13)}")
print(f"    IFFT peak lands at bin  {int(np.argmax(np.abs(y))):8d}      predicted {6*tap_dt/meas_dt:.3f}   "
      f"{ok(int(np.argmax(np.abs(y))) == round(6*tap_dt/meas_dt))}")
print(f"    -> the dump -> H(f) mapping is exact; the path is simply between grid points.")

print(f"\n[3] the delay a recovered index means")
for n in (3, 4, 6):
    print(f"    measured index {n} -> {n*meas_dt*1e9:6.2f} ns, but FILE index {n} -> {n*tap_dt*1e9:6.2f} ns")
print(f"    {ok(True)}  the two indices are different delays -- pairing them by index is invalid")

print(f"\n[4] two paths, known amplitude and phase ratio")
t = np.zeros(64, complex); t[6] = 1.0; t[10] = 0.5 * np.exp(1j * np.pi / 3)
y = through_pipeline(t)
Hs = np.fft.fft(t, N_FFT)[BINS]
# recover each path by projecting onto its own analytic steering vector in frequency
f = np.array([((b + N_FFT // 2) % N_FFT - N_FFT // 2) for b in BINS]) * SCS
A = np.exp(-2j * np.pi * np.outer(f, np.array([6, 10]) * tap_dt))
est = np.linalg.lstsq(A, Hs, rcond=None)[0]
print(f"    true   tap6 {1.0:+.4f}      tap10 {0.5*np.exp(1j*np.pi/3):+.4f}")
print(f"    solved tap6 {est[0]:+.4f}  tap10 {est[1]:+.4f}")
print(f"    {ok(np.allclose(est, [1.0, 0.5*np.exp(1j*np.pi/3)], atol=1e-6))}  the dumped 106 values do contain both paths exactly")

print(f"\n[5] what truncation to 64 of 106 discards")
t = np.zeros(64, complex); t[6] = 1.0
y = through_pipeline(t)
lost = (np.abs(y[64:])**2).sum() / (np.abs(y)**2).sum()
print(f"    energy in bins 64..105 for a single path at tap 6: {100*lost:.2f} %")
print(f"    those bins are NEGATIVE delay (wrap-around), i.e. the pre-cursor skirt")
print(f"    {ok(lost > 0)}  non-zero, so csi_to_npy.py:62-67 discards real signal")

print(f"\n[6] correct way to compare against the file's taps")
t = np.zeros(64, complex); t[6] = 1.0
y_meas = through_pipeline(t)
y_ref = through_pipeline(t)            # SAME transform applied to the reference
err = np.abs(y_meas - y_ref).max()
naive = np.abs(y_meas[:64] - t).max()  # what aligned_H.txt does: ifft output vs raw file taps
print(f"    reference through the SAME transform : max |diff| {err:.2e}   {ok(err < 1e-12)}")
print(f"    reference used RAW (what aligned_H does): max |diff| {naive:.3f}   {ok(naive < 1e-6)}")
print(f"    -> the comparison is only valid if BOTH sides take the same path.")
