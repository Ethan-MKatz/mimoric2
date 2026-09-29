# Review guide — every change from channel file to plot

Written to be reviewed sceptically. It covers **all** modified and added code in the
working tree, says what each change does, and marks what is verified, what is known
wrong, and what rests only on my judgement.

Nothing has been committed since `9eaed1c`, so the working tree *is* the change set.

- Full raw diff: `review/all_changes.patch` (1127 lines, 18 tracked files)
- Summary: `review/all_changes.stat`
- Reproduce either: `git diff -- . ':(exclude)logs'`

---

## 0. The single most important fact for a reviewer

**No OAI signal-processing maths was modified.** Count of removed lines per file:

| file | lines removed | what they were |
|---|---|---|
| `openair1/PHY/NR_UE_TRANSPORT/csi_rx.c` | **0** | pure additions |
| `openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c` | **0** | pure additions |
| `openair1/PHY/NR_UE_ESTIMATION/nr_dl_channel_estimation.c` | **0** | pure additions |
| `openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_dlsch.c` | **0** | pure additions |
| `executables/nr-uesoftmodem.c` | 9 | hardcoded `fopen("...signal_metal_4x4_real.txt")` → env-selected stem |
| `executables/nr-softmodem.c` | 3 | same, uplink |
| `openair2/LAYER2/NR_MAC_UE/nr_ue_scheduler.c` | 3 | three `if (x)` became `if (x) {` to add a counter — identical conditions |

Verify yourself:

```bash
git diff -U0 -- openair1/ openair2/ | grep "^-[^-]"
```

Everything that reads a channel estimate is **read-only observation**. The estimate the
UE and gNB compute is untouched OAI code. The changes that *do* alter behaviour are
confined to four places, listed in §2.

---

## 1. Inventory

### Modified (tracked) — 18 files

| file | role | alters behaviour? |
|---|---|---|
| `radio/rfsimulator/apply_channelmod.c` | **applies the 4×4 channel** | **yes** — §2.1 |
| `radio/rfsimulator/simulator.c` | gates who replays | **yes** — §2.2 |
| `radio/rfsimulator/rfsimulator.h` | one extra arg on `rxAddInput` | signature only |
| `common/config/config_load_configmodule.c` | adds `--ULCHAN` | **yes** — §2.2 |
| `openair1/PHY/NR_TRANSPORT/nr_ulsch_demodulation.c` | out-of-bounds fix | **yes** — §2.3 |
| `executables/nr-uesoftmodem.c` | opens DL tap files, sets up dumps | file selection |
| `executables/nr-softmodem.c` | opens UL tap files, sets up SRS dump | file selection |
| `openair1/PHY/NR_UE_TRANSPORT/csi_rx.c` | **writes the DL dump** | no — §3.1 |
| `openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c` | **writes the UL dump** | no — §3.2 |
| `openair1/PHY/NR_UE_ESTIMATION/nr_dl_channel_estimation.c` | DL power log | no |
| `openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_dlsch.c` | DL rank/CQI to `snr.txt` | no |
| `openair2/LAYER2/NR_MAC_UE/nr_ue_scheduler.c` | diagnostics only | no |
| `CMakeLists.txt` | links `zmq` into the UE | build only |
| `targets/.../gnb.sa.band78...conf` | 4 ports, 256QAM off, noise | **yes** — §4 |
| `ci-scripts/conf_files/nrue.uicc.conf` | pathloss/noise | **yes** — §4 |
| `sims/siso/tti_experiments/docker-compose.yaml` | env wiring | config |
| `sims/siso/tti_experiments/tti_multiue_experiments_demo1.py` | run + teardown | orchestration |
| `.../muApp3_monitor_grafana.py` | xApp monitor | not in this path |

### Added (untracked) — the plotting side

| file | role | trust |
|---|---|---|
| `csi_to_npy.py` | dump → taps `.npy` | **has the grid problem** (§6.2) |
| `export_aligned.py` | TTI match + gain fit → `aligned_H.txt` | **has grid + gain problems** (§6.2, §6.1) |
| `align_twin.py` | prints alignment scores | ok |
| `plot_phase_amp.py` | 4-panel phase/amplitude | panels 1–3 ok, **panel 4 wrong** |
| `plot_phase_amp_ul.py` | uplink driver for the above | ok |
| `plot_channel_freq.py` | 4-panel frequency | **the trustworthy one** |
| `check_phase_amp_independent.py` | independent verifier | shares no code with the above |
| `dump_to_freq_phase.py` | dump → readable table | ok, no processing |
| `validate_array.py`, `plot_channel_validation.py` | older helpers | superseded |
| `compare_twin.sh`, `summarize_run.sh`, `watch_run.sh` | convenience | not in this path |
| `edgeric-v2/muApp4/` | downlink xApp | separate feature |

---

## 2. Changes that alter radio behaviour — review these hardest

### 2.1 `radio/rfsimulator/apply_channelmod.c` — the 4×4 replay

Four changes. The first two are bug fixes to code that was already there; the rest are
robustness.

**(a) Transmit-stream count used as the buffer stride.** The circular buffer interleaves
samples by the *sender's* antenna count, but the code used `channelDesc->nb_tx`, which is
*this node's own* transmit count:

```c
const int nbTx = (nbTxStream > 0) ? nbTxStream : channelDesc->nb_tx;
```

`nbTxStream` is new, passed from `simulator.c` as `ptr->th.nbAnt` (the packet header).
**Why it matters:** if the two differ, the buffer is read scrambled and every sample is
formed from the wrong antenna.

*Confirmed:* the sender writes that header itself in `rfsimulator_write_internal`
(`simulator.c:704`, `samplesBlockHeader_t header = {nsamps, nbAnt, timestamp}`), where `nbAnt`
is its own transmit count — so `th.nbAnt` on the receive side is the sender's stream count, and
the interleave stride is right.

**(b) Line buffer too small.** A 4×4 × 64-tap line is ~4.2 kB; the buffer was 2000 bytes:

```c
#define _MIMO_MAXTAPS 1024
#define _MIMO_MAXLINE (_MIMO_MAXTAPS * 20)
char strr[_MIMO_MAXLINE], stri[_MIMO_MAXLINE];
```

A short buffer splits one line over two reads and silently de-syncs the receive rows.
`readTapLine()` now also warns once and discards the remainder rather than de-syncing.

**(c) Tap cache widened** from `8*128` to `_MIMO_MAXTAPS` (1024) — 4 tx × 64 taps = 256 fits
either way, but `nbTx*taplen` is the real bound.

**(d) A one-shot `[REPLAY-DIAG]` line** to stderr. Check it in the logs; it prints the taps
actually loaded.

**The maths itself is unchanged** — the complex multiply–accumulate at the bottom of
`rxAddInput` is original OAI, only re-indexed by `txAnt*taplen + l`.

### 2.2 `simulator.c` + `config_load_configmodule.c` — `--ULCHAN`

```c
if ( ptr->channel_model != NULL && (gnb1_ue0==0 || ul_chan_enable) && taplen>0) {
```

Originally only the UE (`gnb1_ue0==0`) applied a channel. With `--ULCHAN 1` the gNB does the
same on its receive path, which is what makes the uplink carry the replayed channel instead
of rfsim's built-in placeholder. **Default is 0, so this is opt-in and changes nothing unless
the flag is passed.**

### 2.3 `nr_ulsch_demodulation.c` — a real bounds fix

```c
- for (int re = 0; re < buffer_length && ...; re += DS_SC) {
+ for (int re = 0; re < nb_re_pusch && ...; re += DS_SC) {
```

Only `nb_re_pusch` REs are written for a symbol, so walking to `buffer_length` reads the next
symbol's unwritten block as zeros, and past the row end for a late measurement symbol. This is
the one place where I changed a loop bound in signal-processing code. It affects the MIMO-RIC
channel export, not demodulation output.

---

## 3. The capture path — additions only

### 3.1 `csi_rx.c` — the downlink dump

Three separate additions:

1. **Globals** (~line 48): `tt_csi_every`, `tt_csi_max`, the `FILE*`, the ZMQ socket.
2. **The dump** (lines 1033-1046) — see below.
3. **A ZMQ publisher** (~1053-1090) for the live xApp. Independent of the file.

```c
fprintf(fpdlcsi, "CSI %d %d %d %d %d %d", tt_csi_written, proc->frame_rx, proc->nr_slot_rx, nrx, ntx, nsc);
for (int ant_rx = 0; ant_rx < nrx; ant_rx++)
  for (int port_tx = 0; port_tx < ntx; port_tx++)
    for (int rb = start_rb; rb < start_rb + nr_of_rbs; rb++) {
      uint16_t k = (frame_parms->first_carrier_offset + rb * NR_NB_SC_PER_RB) % frame_parms->ofdm_symbol_size;
      const c16_t *h = (const c16_t *)&csi_rs_estimated_channel_freq[ant_rx][port_tx][k + mem_offset];
      fprintf(fpdlcsi, " %d %d", h->r, h->i);
    }
```

**What to check:** it only *reads* `csi_rs_estimated_channel_freq`, which OAI filled. The
subcarrier index `k` is the same formula OAI's own interpolation writes at (`csi_rx.c:398+`),
so the dump samples exactly the points the estimator produced — no interpolation of mine.

### 3.2 `gNB_scheduler_ulsch.c` — the uplink dump

```c
fprintf(fpulsrs, "SRS %d %d %d %d %d %d", tt_srs_written, frame, slot, Ng, Nu, Np);
for (int gI = 0; gI < Ng; gI++)
  for (int uI = 0; uI < Nu; uI++)
    for (int pI = 0; pI < Np; pI++) {
      const int idx = uI * Ng * Np + gI * Np + pI;   // source layout, nfapi
      ...
    }
```

The index is deliberately re-ordered so the file comes out `[rx][tx][freq]` like the downlink
one. **What to check:** that `uI*Ng*Np + gI*Np + pI` matches the nfapi layout — it is documented
in `nfapi_nr_interface_scf.h` and implemented at `phy_procedures_nr_gNB.c:676-715`.

---

## 4. Config changes that change the radio

| change | file | why | risk |
|---|---|---|---|
| `force_256qam_off = 1` | gnb conf | UE segfaulted in `nr_256qam_llr`; two cores in `logs/`. Forces MCS table 0. | caps throughput; does not touch the channel |
| `pdsch_AntennaPorts_XP=2, N1=2` | gnb conf | 4 DL ports, required for 4×4 | intended |
| `ploss_dB 20 → 0`, `noise_power_dB -4 → -20` | nrue conf | let the replayed channel dominate | **makes the link unrealistically clean** — this is why CQI pins at 15 |
| `noise_power_dB 0 → -10` | gnb conf | same, uplink | same |

The noise settings are a deliberate choice worth arguing about: they make the replay easy to
validate but the link unrealistically good. Any KPI-based conclusion inherits that.

---

## 5. The plotting path, in order

```
dl_csi_ue1.txt ──┬─> csi_to_npy.py ─> export_aligned.py ─> aligned_H.txt ─> plot_phase_amp.py
                 │                          │
signal_*_real/imag ──────────────────────────┤
                 │                          └─> align_summary.txt
                 └─> plot_channel_freq.py (reads the dump DIRECTLY) ─> channel_freq_dl.png
```

Two routes. The frequency route reads the dump directly and is the one to trust. The
phase-amplitude route goes through a tap conversion that has a known defect (§6.2).

**`plot_channel_freq.py`** — three parts worth reading:

- `load_dump()` (lines 39-59) — the parser, ten lines.
- Lines 118-128 — sampling the truth onto the measurement's frequencies:
  ```python
  fco = N_FFT - (106 * 12) // 2      # = 1412
  bins = [(fco + 12 * rb) % N_FFT for rb in range(nsc)]
  Sf = np.fft.fft(S, N_FFT, axis=-1)[..., bins]
  ```
  **This line was wrong before** — I used bins `0, 12, 24…`, ignoring that the used
  subcarriers wrap around the FFT. Correlation went from −0.180 to +0.846 when fixed.
- The gain fit (`--gain band` default) and the snapshot-wide normalisation.

**`plot_phase_amp.py`** — writes `phase_amp_series.txt` by calling `get_ydata()` on the
drawn `Line2D` objects, so the table cannot drift from the figure.

**`check_phase_amp_independent.py`** — imports only numpy, parses the dump itself, runs its
own TTI search, compares gain-free ratios. Deliberately shares nothing with the above.

---

## 6. Known defects — not yet fixed

### 6.1 Gain fit biased ≈0.7 dB low
`export_aligned.py:44` fits one complex scale over all 64 taps. Taps past the echo hold only
noise, which drags the fit down. Measured: −0.80 dB (sd 0.25) versus −0.00 dB (sd 0.02) for an
in-band fit. `plot_channel_freq.py` already uses the in-band fit; `aligned_H.txt` does not.

### 6.2 Tap grids do not match
File taps are 16.28 ns apart; taps reconstructed from 106 per-RB samples are 26.21 ns apart.
`aligned_H.txt` pairs "tap k" with "tap k" regardless. Only the peak row (tap 6) is meaningful.
The 106→64 truncation also discards the wrapped precursors (2.1 % of energy).

**Consequences:** panel 4 of the phase-amplitude plots is wrong, and `aligned_H.txt` must not be
used as training data. **Fix:** put the source through the measurement's own path — sample at the
106 RB frequencies, IFFT, keep all 106 bins.

### 6.3 TTI labels are inferred
The replay never records which TTI it applied. Every label comes from a correlation search, and
2 of 38 downlink labels are ambiguous (record 22 scores 0.999 at both TTI 478 and TTI 722).

---

## 7. What is actually verified

| claim | evidence | independent of me? |
|---|---|---|
| Channel files match your originals | md5 `acce3ae4…`, `746b8d48…` | yes |
| Ground truth matches your own plot | 0.01 dB across all four antennas | **yes — your script** |
| Replay reproduces the file | 0.18 dB / 1.3° median (DL), 0.12 dB / 0.7° (UL) | separate program |
| Plot shows the replay | 0.11 dB / 1.0° median (DL) | separate program |
| Deep fades unreliable | up to 7.6 dB / 49°, all 15–20 dB below rx0 | separate program |

Re-run the last three yourself:

```bash
python3 check_phase_amp_independent.py        # downlink
python3 check_phase_amp_independent.py --ul   # uplink
```

---

## 8. What no check covers

- **Absolute level.** Everything above uses ratios between antennas, so a common scale error is
  invisible — including the 0.7 dB in §6.1.
- **Rendering.** The checks read numbers, not pixels. The legend bug (a second `ax.legend()` call
  silently deleting the first) would not be caught.
- **The ground-truth side.** If my sampling of the file were wrong again, "plot vs replay" would
  still pass; only "replay vs truth" would move. They are reported separately for that reason.
- **Anything tap-based.** Deliberately avoided.

## 9. Defects found and fixed this cycle, for calibration

| defect | how it surfaced |
|---|---|
| Truth sampled at the wrong FFT bins | your scepticism about the plot's structure |
| Per-trace normalisation erasing antenna spread | **your own validation plot** |
| Measurement never scaled to the truth (54 dB) | exposed once the normalisation bug was removed |
| Gain fit 0.8 dB low | chasing the residual after the above |
| Tap grid mismatch | your question "is it all the TTIs for one tap?" |
| Legend silently deleted | you noticed it missing |
| "Precursors absent in the measurement" — false | re-derived while writing the slides |

Five of seven were found by you or by a question you asked, not by me. That is the honest base
rate to apply to anything here that rests on my judgement rather than on a number you can re-run.
