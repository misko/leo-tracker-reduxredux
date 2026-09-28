# Screen-only phasor factoring

This report-local change reduces trigonometric work in the approximate
conditioned screen. It computes 32 local phasors and an exact anchor every
32 samples, then multiplies them. The original per-sample FP64 rotation stays
in the exact near-maximum rechecks and all final scoring. Irregular grids also
retain the original rotation path. Every sample, bin, frame, and candidate is
still evaluated.

## Measured ARM effect

Saved IQ runs on CPU0 of PLUTO+ 192.168.1.15, with no RF collection or concurrent
capture. Samples are processed from RAM. File transfer and workspace creation
are outside kernel timings; first-use CZT setup remains inside the search.

| Measurement, 2.5 MS/s | Previous CZT | Factored screen | Speedup |
| --- | ---: | ---: | ---: |
| Four windows, three repeats | 1.559840 s/window | 1.542867 s/window | 1.0110× |
| Four dual-RX dwells, 88 windows | 34.331764 s/dwell | 33.912983 s/dwell | 1.01235× |
| Conditioned stage, same dwells | 8.142130 s/dwell | 7.752529 s/dwell | 1.0503× |

The full-dwell saving is about **0.419 CPU seconds**, or **1.22% less time**.
This is a small optimization, not a change in real-time feasibility.

Four additional matched probes per rate, one repetition each:

| Rate (MS/s) | Previous seconds/window | Factored seconds/window | Speedup |
| ---: | ---: | ---: | ---: |
| 2.5 | 1.569248 | 1.551122 | 1.01169× |
| 5 | 4.398393 | 4.362704 | 1.00818× |
| 7.5 | 8.888104 | 8.834414 | 1.00608× |
| 10 | 14.112965 | 14.040613 | 1.00515× |

## Exact windows and hit recovery

The ARM full-dwell cohort executes **88 overlapping 20 ms windows**, eight
candidate GLRTs per window, and recovers **119/119 individual positive hits**
and **49/49 positive windows**. Every one of its 704 candidate objects matches
the previous CZT result exactly. All candidate objects and coarse grids also
match in the repeated probes and all-rate ARM probes.

The larger host run processes 704 dwells from all 88 DS7 recordings (eight
selected dwells per recording), or **0.361% of 194,934 DS7 dwells**:

| Rate | 20 ms windows run | Positive windows recovered / baseline | Individual hits recovered / baseline |
| ---: | ---: | ---: | ---: |
| 2.5 MS/s | 3,344 | 1,682 / 1,682 | 4,573 / 4,573 |
| 5 MS/s | 4,752 | 1,874 / 1,874 | 5,466 / 5,466 |
| 7.5 MS/s | 4,048 | 1,933 / 1,933 | 5,186 / 5,186 |
| 10 MS/s | 3,344 | 1,518 / 1,518 | 4,356 / 4,356 |
| **Total** | **15,488** | **7,007 / 7,007** | **19,581 / 19,581** |

All **123,904 candidate objects** are exactly identical to the previous CZT
host run, with zero added hits. The frozen original baseline still has the
same inherited negative-window mismatch at ordinal306, RX0, probe3, four
ordered ranks. No new mismatch was introduced. Host runtime is not used to
infer ARM speed.

## Validation and limits

- Normal host and ASAN/UBSAN builds pass numerical and conditioned integration
  tests. The integration test now covers all four sample rates, zero input and
  template energy, irregular-grid fallback, and near-tied bins requiring two
  exact rechecks.
- The all-rate conditioned integration test passes on ARM, with a hashed
  execution receipt in `arm-unit-v1/`.
- The 64-dwell preliminary host cohort recovered 1,669/1,669 hits with zero
  original-baseline audit errors. The 704-dwell result and strict complete
  candidate comparison are in `host704/`.
- `paired_cohort.py` checks input identity, unique complete window inventories,
  native success, and equality of all emitted candidate fields. The existing
  independent summary tool separately reproduces original-baseline hit counts.
- Raw ARM original-oracle receipts still say `passed: false` for inherited
  FP32 coarse differences. Paired comparisons against the preceding build
  pass; the raw receipts are not relabeled.

The approximate screen's guard remains an engineering guard, not a universal
proof. Build sources and compiler commands are archived in `builds/`; the
builder reuses the sealed CZT build recipe. No production pipeline changed.

This experiment is independent of the higher-rate coarse-FFT integration.
Their gains must not be multiplied into a claimed combined measurement.
At **33.913 CPU seconds per 120 ms dual-RX dwell**, this workload is still
about **283×** the continuous single-core budget, or **471×** a 60%-CPU analysis
budget. Simultaneous capture and 40% headroom remain unverified.
