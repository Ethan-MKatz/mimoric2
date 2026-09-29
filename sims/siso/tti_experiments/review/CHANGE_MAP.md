# Change map — every line, by file

Line numbers are **current-file** line numbers, so you can open the file and go straight there.
Generated from `git diff -U0 -- . ':(exclude)logs'`, not from memory. Regenerate with:

```bash
git diff -U0 -- . ':(exclude)logs' | grep -E '^(\+\+\+|@@)'
```

Nothing is committed since `9eaed1c`, so the working tree is the whole change set.
Totals: **18 files modified**, **~430 lines added**, **~40 lines changed**, **15 lines removed**.

---

# PART A — files I modified (existing OAI code)

## A1. `radio/rfsimulator/apply_channelmod.c` — applies the 4×4 channel
The single most important file. This is where your tap file becomes received samples.

| lines | kind | what I did |
|---|---|---|
| 28-29 | added | `#include <string.h>`, `#include <stdbool.h>` for the new helper |
| 50-54 | added | `_MIMO_MAXTAPS` (1024) and `_MIMO_MAXLINE` (20 kB) — the real bound is `nb_tx*taplen` |
| 83-107 | added | **`readTapLine()`** — reads one tap line, rewinds at EOF so the 800-TTI file loops, and warns once if a line still doesn't fit instead of silently de-syncing |
| 115-116, 119 | changed | `rxAddInput` signature gains `int nbTxStream`; buffers `strr`/`stri` go from `[2000]` to `[_MIMO_MAXLINE]` |
| 205-209 | changed | **the stride fix** — `nbTx` now comes from the sender's stream count, not `channelDesc->nb_tx` |
| 219-220 | changed | `Hr_cache` / `Hi_cache` widened from `[8*128]` to `[_MIMO_MAXTAPS]` |
| 241, 243, 246-248, 251-252 | changed | the file-read loop now calls `readTapLine()` and bounds by `_MIMO_MAXTAPS` |
| 255-267 | added | one-shot `[REPLAY-DIAG]` to stderr: taplen, nbTx, nbRx, pathloss, noise, first tap per tx |

**Untouched:** the convolution itself (the complex multiply–accumulate over `txAnt` and `l`). That is stock OAI; I only re-indexed nothing — it already used `txAnt*taplen + l`.

## A2. `radio/rfsimulator/rfsimulator.h`
| lines | kind | what I did |
|---|---|---|
| 33-34 | changed | added the `int nbTxStream` parameter to the `rxAddInput` declaration |

## A3. `radio/rfsimulator/simulator.c` — who replays, and the stream count
| lines | kind | what I did |
|---|---|---|
| 123 | added | `extern int ul_chan_enable;` |
| 1028-1031 | changed | **the gate**: `gnb1_ue0==0` became `(gnb1_ue0==0 \|\| ul_chan_enable)` so the gNB can replay too |
| 1045-1046 | changed | pass `ptr->th.nbAnt` (the sender's antenna count, from the packet header) into `rxAddInput` |

## A4. `common/config/config_load_configmodule.c` — the `--ULCHAN` flag
| lines | kind | what I did |
|---|---|---|
| 64-69 | added | comment block + `int ul_chan_enable = 0;` |
| 275 | added | `int ULCHANIdx = -1;` |
| 322-326 | added | parse `--ULCHAN <0/1>` from argv |
| 502-505 | added | mark those two argv entries as processed so OAI doesn't reject them |

## A5. `executables/nr-uesoftmodem.c` — UE side: picks the DL tap file, opens every dump
| lines | kind | what I did |
|---|---|---|
| 30 | added | `#include <zmq.h>` |
| 99-103 | added | externs for the CSI dump: `fpdlcsi`, `tt_csi_zmq_ctx`, `tt_csi_zmq_pub`, `tt_csi_every`, `tt_csi_max` |
| 122-135 | added | `extern FILE *fpdlch;` and the **`openTapFile()`** helper (builds `channel/<stem>_<part>.txt`, logs if missing) |
| 308-331 | changed | **replaced 9 hardcoded `fopen()` calls** with `TT_CHAN_SIGNAL` / `TT_CHAN_JAMMER` stems via `openTapFile`; opens the DL power log from `TT_DL_CHAN_LOG` |
| 333-349 | changed | opens the CSI dump from `TT_DL_CSI_LOG`, reads `TT_DL_CSI_EVERY` / `TT_DL_CSI_MAX` |
| 351-373 | changed | sets up the ZMQ publisher from `TT_DL_CSI_ZMQ` (PUB socket, shallow queue so a slow subscriber can't stall the PHY) |

## A6. `executables/nr-softmodem.c` — gNB side: picks the UL tap file, opens the SRS dump
| lines | kind | what I did |
|---|---|---|
| 116-118 | added | externs `fpulsrs`, `tt_srs_every`, `tt_srs_max` |
| 670-704 | changed | **replaced 3 hardcoded `fopen()` calls** with the `TT_UL_CHAN_SIGNAL` stem (670-687), then opens the SRS dump from `TT_UL_SRS_LOG` with `TT_UL_SRS_EVERY` / `TT_UL_SRS_MAX` (689-704) |

## A7. `openair1/PHY/NR_UE_TRANSPORT/csi_rx.c` — writes the downlink dump
| lines | kind | what I did |
|---|---|---|
| 41-62 | added | `#include <zmq.h>`; globals `fpdlcsi`, `tt_csi_every = 1`, `tt_csi_max = 2000`, `tt_csi_zmq_ctx`, `tt_csi_zmq_pub` |
| 1009-1092 | added | the whole capture block: the every-N / max gate (1023), the **text dump** (1033-1046), and the **ZMQ publish** (~1053-1090) |

**0 lines removed.** The estimation above it is untouched stock OAI; this only reads `csi_rs_estimated_channel_freq`.

## A8. `openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c` — writes the uplink dump
| lines | kind | what I did |
|---|---|---|
| 42-51 | added | globals `fpulsrs`, `tt_srs_every = 1`, `tt_srs_max = 2000` |
| 1478-1515 | added | the SRS channel-matrix dump, re-ordered to `[rx][tx][PRG]` so it matches the DL file |

**0 lines removed.**

## A9. `openair1/PHY/NR_UE_ESTIMATION/nr_dl_channel_estimation.c` — DL power log
| lines | kind | what I did |
|---|---|---|
| 37-39 | added | `#include <math.h>`, `FILE *fpdlch = NULL;` |
| 836-853 | added | one `DLCH` line per SSB: per-rx-antenna power in dB. **Power only** — the squaring discards phase |

**0 lines removed.**

## A10. `openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_dlsch.c` — rank + CQI into snr.txt
| lines | kind | what I did |
|---|---|---|
| 1102-1111 | added | writes `TTI Index:` / `DL RANK:` / `DL CQI:` in the format the experiment scripts already parse |

**0 lines removed.**

## A11. `openair1/PHY/NR_TRANSPORT/nr_ulsch_demodulation.c` — the only maths I touched
| lines | kind | what I did |
|---|---|---|
| 1679-1683 | changed | loop bound `buffer_length` → `nb_re_pusch`, plus a 3-line comment. Only `nb_re_pusch` REs are written per symbol, so the old bound read unwritten memory |

## A12. `openair2/LAYER2/NR_MAC_UE/nr_ue_scheduler.c` — diagnostics only
| lines | kind | what I did |
|---|---|---|
| 1337-1344 | added | logs UE state transitions (`TT-UE-STATE`) |
| 2741-2748, 2750, 2754-2755, 2757, 2775-2776, 2778-2779 | changed/added | counters for why CSI-RS reception stops being scheduled. **The 3 "removed" lines are `if (x)` becoming `if (x) {`** — identical conditions, braces added so a counter fits |

Both are leftovers from misdiagnosing the crash. Harmless, and removable.

## A13. `CMakeLists.txt`
| lines | kind | what I did |
|---|---|---|
| 2096 | changed | `-Wl,--end-group z dl)` → `-Wl,--end-group z dl zmq)` for `nr-uesoftmodem` |

## A14. `targets/PROJECTS/GENERIC-NR-5GC/CONF/gnb.sa.band78.fr1.106PRB.usrpb210.conf`
| lines | kind | what I did |
|---|---|---|
| 27 | changed | comment describing the 1×4 ULA on each node |
| 35-40 | added | **`force_256qam_off = 1;`** plus the comment explaining the `nr_256qam_llr` crash |
| 279 | changed | `noise_power_dB` 0 → −10 |

`pdsch_AntennaPorts_XP = 2` / `N1 = 2` were already present.

## A15. `ci-scripts/conf_files/nrue.uicc.conf`
| lines | kind | what I did |
|---|---|---|
| 19-20 | changed | `ploss_dB` 20 → 0, `noise_power_dB` −4 → −20 |

## A16. `sims/siso/tti_experiments/docker-compose.yaml`
| lines | kind | what I did |
|---|---|---|
| 27-37 | added | gNB env: `TT_UL_CHAN_SIGNAL`, `TT_UL_SRS_LOG`, `TT_UL_SRS_EVERY`, `TT_UL_SRS_MAX` |
| 40 | changed | gNB entrypoint gains `--ULCHAN 1` |
| 71-84 | added | UE env: `TT_CHAN_SIGNAL`, `TT_DL_CHAN_LOG`, `TT_DL_CSI_LOG`, `TT_DL_CSI_ZMQ` |
| 87 | changed | UE entrypoint |
| 117-126 | added | muApp3 env: `TT_CHAN_LOG`, `TT_CHAN_LOG_RAW`, `TT_CHAN_LOG_EVERY` |

## A17. `sims/siso/tti_experiments/tti_multiue_experiments_demo1.py`
| lines | kind | what I did |
|---|---|---|
| 3 | added | `import os` |
| 17-21 | changed | `CHAN_STEM` from `sys.argv[3]`, default `signal_metal_4x4` |
| 47-57 | added | gNB env block (UL replay + SRS dump) |
| 60 | changed | gNB entrypoint: `--rfsimulator.options chanmod --TAP {start_tap} --ULCHAN 1` |
| 90-99 | added | muApp3 env block |
| 315-328 | added | UE env block (DL stem, CSI log, ZMQ port per UE) |
| 331 | changed | UE entrypoint |
| 410-412 | changed | `TT_RUN_SECONDS` (default 1800) instead of a fixed sleep |
| 681-732 | added | **the whole teardown pipeline**: copies logs into `plot/ue1_64/`, then runs csi_to_npy → export_aligned → plot_phase_amp → align_twin → plot_channel_freq, and the UL equivalents |

## A18. `sims/siso/tti_experiments/edgeric-v2/muApp3/muApp3_monitor_grafana.py`
| lines | kind | what I did |
|---|---|---|
| 46-76, 83, 107, 121-150 | changed/added | UL channel logging from the RIC report — not part of the channel→plot path |

---

# PART B — files I wrote from scratch

Every line in these is mine. None existed before.

## B1. The plotting path (in `sims/siso/tti_experiments/`)

| file | lines | what it does |
|---|---|---|
| `csi_to_npy.py` | 76 | parses a dump, IFFTs to taps. **Carries the 26.21 ns grid defect** |
| `export_aligned.py` | 98 | correlation TTI search (:40-42), one complex gain per snapshot (:44), writes `align_summary*.txt` and `aligned_H*.txt` |
| `align_twin.py` | 61 | prints alignment scores |
| `plot_channel_freq.py` | 263 | the frequency figure, both directions. **The trustworthy one** — reads the dump directly |
| `plot_phase_amp.py` | 162 | the phase/amplitude figure; writes its CSV from the drawn lines |
| `plot_phase_amp_ul.py` | 75 | uplink driver over the same three scripts |
| `dump_to_freq_phase.py` | 90 | dump → readable table with `freq_MHz`, `amp_dB`, `phase_deg` |
| `check_phase_amp_independent.py` | 122 | independent verifier; numpy only, shares no code with the above |
| `validate_array.py` | 237 | earlier array-geometry checks |
| `plot_channel_validation.py` | 160 | earlier validation figure, superseded |
| `compare_twin.sh` | 59 | convenience wrapper |
| `summarize_run.sh` | 69 | run summary |
| `watch_run.sh` | 37 | live log watch |

## B2. The audit material (`sims/siso/tti_experiments/review/`)

| file | lines | what it does |
|---|---|---|
| `REVIEW_GUIDE.md` | 308 | prose guide with verification commands |
| `CHANGE_MAP.md` | this file | line-by-line map |
| `PREDICTIONS_metal.md` | 103 | 16 numeric predictions, written before the metal run |
| `audit_parser_unit_test.py` | 103 | synthetic channel with an analytic answer through the parser |
| `loopback_test.py` | 106 | perfect receiver through the real plotting code |
| `all_changes.patch` | 1127 | the raw diff |
| `all_changes.stat` | — | the summary |

## B3. The xApp
| file | lines | what it does |
|---|---|---|
| `edgeric-v2/muApp4/muApp4_channel_xapp.py` | 155 | consumes the live CSI over ZMQ (`--mode dl` / `--mode ul`) |

## B4. The archives (`sims/siso/tti_experiments/datasets/`)
`20260917_concrete4x4_nojam/` and `20260921_metal4x4_nojam/` — frozen run data, each with its own
`README.md`, `SHA256SUMS`, and a `provenance/` copy of the code that produced it.

---

# PART C — the path, in order

```
channel/<stem>_{real,imag}.txt
   │  opened by     nr-uesoftmodem.c:311-318   (DL)   nr-softmodem.c:674-686 (UL)
   ↓
apply_channelmod.c:241-252    read one line per rx antenna
apply_channelmod.c:334-386    convolve: 4 tx × 64 taps per output sample   [STOCK OAI MATHS]
   ↓
simulator.c:1028-1031         gate: UE always, gNB only with --ULCHAN 1
   ↓
        [ OAI estimates the channel — completely untouched ]
   ↓
csi_rx.c:1033-1046            DL dump        gNB_scheduler_ulsch.c:1497-1508   UL dump
   ↓
plot_channel_freq.py:39-59    parse  →  :118-130 truth to the same bins  →  :168-189 draw
csi_to_npy.py:61              IFFT   →  export_aligned.py:42,44  →  plot_phase_amp.py:58
```
