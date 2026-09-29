# Predictions for the metal run — written BEFORE the run

Recorded 2026-09-21, before any metal run data exists. `plot/ue1_64/` still holds the
17 September concrete data; the only metal input is the channel file itself.

**Why this file exists.** Every fix in the pipeline was made while looking at *concrete*
results, twice after being shown that the output was wrong. That is the setup for tuning a
pipeline until it agrees, rather than fixing it. Metal is a channel nothing has been fitted
to, so it is a held-out test — but only if the expected numbers are committed in advance.

If these predictions fail, the fixes were concrete-specific and you should distrust them.

---

## Ground truth, computed from `signal_metal_4x4_{real,imag}.txt` alone

| property | metal | concrete (for contrast) |
|---|---|---|
| dominant tap | 6, holding **85.0 %** | 6, holding 92.1 % |
| in-band ripple, peak-to-peak | **1.37 dB** median | 0.52–1.08 dB |
| level swing over 800 TTIs | **16.4 dB** | 31.7 dB |
| antenna spread vs rx0 | median **4.01 dB**, p95 13.31 dB | 0 / −0.6 / −2.4 / −4.2 dB at TTI 102 |
| adjacent-subcarrier change | **0.03 %** → CSI-RS CDM leakage −76.6 dB | 1.88 % → −40.6 dB |

---

## Predictions

### A. The independent check (`check_phase_amp_independent.py`)

| # | prediction | fails if |
|---|---|---|
| A1 | DL replay vs truth: amplitude median ≤ **0.35 dB** | > 0.35 dB |
| A2 | DL replay vs truth: phase median ≤ **2.5°** | > 2.5° |
| A3 | UL replay vs truth: amplitude median ≤ **0.35 dB**, phase ≤ **2.5°** | either exceeded |
| A4 | DL plot vs replay: amplitude median ≤ **0.25 dB**, phase ≤ **2.0°** | either exceeded |
| A5 | UL plot vs replay: amplitude median ≤ **0.25 dB**, phase ≤ **2.0°** | either exceeded |
| A6 | Worst-case DL amplitude error **smaller** than concrete's 7.6 dB — predict < **5 dB** | ≥ 7.6 dB |

A6 follows from metal's level swing being half of concrete's: fewer deep fades, so fewer
low-confidence points. If metal produces *more* extreme outliers than concrete, my
"deep fades explain the outliers" story is wrong.

### B. Alignment

| # | prediction | fails if |
|---|---|---|
| B1 | Tap shift = **6** for the large majority of snapshots | scattered shifts |
| B2 | Best-snapshot correlation ≥ **0.88** both directions | below |
| B3 | Own TTI search agrees with `align_summary` on ≥ **90 %** of DL snapshots | below |
| B4 | UL still collapses to ~**5 distinct** source TTIs | more — structural, material-independent |

### C. Frequency plots

| # | prediction | fails if |
|---|---|---|
| C1 | Curves visibly **wavier** than concrete — truth ripple 1.37 dB vs 0.5–1.1 dB | as flat as concrete |
| C2 | Measured ripple tracks truth ripple within ~**0.7 dB** | measured flat while truth is not |
| C3 | DL magnitude error IQR ≤ **0.6 dB** | above |
| C4 | Antenna traces **further apart** than concrete's 4.2 dB span — median spread 4.01 dB, p95 13.3 dB | all bunched together |

### D. Shapes

| # | prediction |
|---|---|
| D1 | DL dump `4 × 4 × 106`, UL dump `4 × 4 × 104` |
| D2 | `[REPLAY-DIAG]` reports `taplen=64 nbTx=4 nbRx=4` |
| D3 | Both logs name `signal_metal_4x4` |

---

## Why metal is a *harder* test than concrete for one specific fix

Concrete is nearly flat in frequency (0.5–1.1 dB ripple). A wrong RB→FFT bin mapping still
produces a flat-looking curve there, so the plot can look plausible while being wrong — which
is exactly what happened. Metal has 1.37 dB of real structure, so a wrong mapping misaligns
features that are actually visible and decorrelates the comparison badly.

**So C1 and C2 together are the strongest single test of the bin-mapping fix.** If the measured
curve has structure that sits where the truth's structure sits, the mapping is right for a
channel it was never tuned on.

---

## What would indicate the fixes are concrete-specific

| symptom | what it implicates |
|---|---|
| A1/A2 fail but A4/A5 pass | the replay, or my sampling of the truth — not the plotting |
| A4/A5 fail but A1/A2 pass | the plotting path is concrete-tuned |
| C2 fails — measured flat, truth wavy | bin mapping still wrong; concrete's flatness was hiding it |
| A6 fails — worse outliers than concrete | the deep-fade explanation is wrong |

---

## The check that doesn't involve me at all

`check_phase_amp_independent.py` is still my code. The genuinely independent test is the one
you already ran for concrete: your own script, reading `channel/signal_metal_4x4_*` directly,
plotting |H| against frequency for the four antennas at one TTI. Then compare it against
`channel_freq_dl.png` from the run.

That comparison caught the normalisation bug. Nothing I write here is as strong.
