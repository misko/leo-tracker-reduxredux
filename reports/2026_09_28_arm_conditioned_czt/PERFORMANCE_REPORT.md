# Conditioned CZT: measured ARM speed and DS7 recovery

The conditioned frequency search now uses cached FP32 FFT convolution, with
the existing FP64 near-maximum verification and final GLRT. It improves the
qualified 2.5 MS/s ARM implementation by **1.079×** on complete dual-RX dwells.
It preserves every candidate object in both the 704-dwell host cohort and the
four-dwell ARM cohort relative to the preceding optimized implementation.

## Actual 20 ms windows and individual hits

The larger recovery run uses 704 saved DS7 dwells, eight from each of its 88
recordings. It processes **15,488 overlapping 20 ms receiver windows** and
**123,904 candidate GLRT evaluations**. It runs on the host to make a larger
quality test practical; this is not an ARM timing result. A dual-RX 120 ms dwell
contains 22 windows, with 10 ms stride and eight retained candidates per window.

| Rate (MS/s) | Dwells | 20 ms windows executed | Baseline positive windows | Positive windows recovered | Baseline individual hits | Individual hits recovered |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2.5 | 152 | 3,344 | 1,682 | 1,682 | 4,573 | 4,573 |
| 5 | 216 | 4,752 | 1,874 | 1,874 | 5,466 | 5,466 |
| 7.5 | 184 | 4,048 | 1,933 | 1,933 | 5,186 | 5,186 |
| 10 | 152 | 3,344 | 1,518 | 1,518 | 4,356 | 4,356 |
| **Total** | **704** | **15,488** | **7,007** | **7,007** | **19,581** | **19,581** |

Recovery is 100% for both positive metrics, with no added hits. A positive
candidate has final margin at least 0.025. Matching to the original baseline
uses the frozen one-to-one two-sample/8 kHz tolerances. Additionally, all
123,904 full candidate objects are exactly identical to the preceding scoped
coarse optimization, including its negative candidates. See `HOST_AUDIT.md`
and `paired-audit.json` for the independent audit.

This is **0.361% of DS7's 194,934 dwells**, not the complete dataset. The older
original baseline has one known negative-window ordering difference at ordinal
306, RX0, probe3, ranks1–4. That difference already exists in the preceding
FP32-coarse implementation; CZT introduces no further difference here.

## Single-core ARM results at 2.5 MS/s

Saved IQ is processed from RAM on CPU0 of the development PLUTO+ at
192.168.1.15. No RF collection or simultaneous capture runs during these tests.
Timings exclude file transfer and workspace setup; first-use CZT planning is
inside the search. Repeated probe totals are averages, while per-stage probe
timings in raw output refer to the last repetition.

| Measurement | Preceding scoped build | CZT build | Speedup |
| --- | ---: | ---: | ---: |
| Four matched windows, three repeats each | 1.681056 s/window | 1.559840 s/window | 1.0777× |
| Four full dual-RX dwells, 88 windows | 37.037486 s/dwell | 34.331764 s/dwell | 1.0788× |
| Conditioned stage within those dwells | 10.842146 s/dwell | 8.142130 s/dwell | 1.3316× |

The full ARM cohort executes **88 windows / 704 candidate GLRTs**, recovers
**119/119 individual hits** and **49/49 positive windows**, and has identical
candidate objects to the preceding ARM build. Probe coarse grids are also
bit-identical. See `arm-cohort-v3/summary.json`, its `paired-audit.json`, and
`probe-comparison.json`.

After this change, per-dwell CPU time includes 19.778 s coarse search, 8.142 s
conditioned search, 3.850 s fine FFT, 1.700 s verification, and 0.483 s final
GLRT. Coarse search accounts for about 58% of the total and remains the largest
optimization target.

## All-rate ARM probes

Four matched windows per rate, one execution each, using the same complete
search. All 128 candidate objects match the preceding ARM build exactly, and
all 16 coarse grids are bit-identical (`allrates-comparison.json`).

| Rate (MS/s) | Preceding CPU seconds/window | CZT CPU seconds/window | Speedup |
| ---: | ---: | ---: | ---: |
| 2.5 | 1.687710 | 1.569248 | 1.0755× |
| 5 | 4.663339 | 4.398393 | 1.0602× |
| 7.5 | 8.902456 | 8.888104 | 1.0016× |
| 10 | 14.476538 | 14.112965 | 1.0258× |

The 7.5 MS/s result is effectively neutral at this repetition count; it does
not establish a meaningful speed improvement. The FFT length increases from
8,192 at 5 MS/s to 16,384 at 7.5 MS/s, while the coarse-search share also grows
with rate. Recommend this as a measured 2.5 MS/s research improvement, with
correctness coverage at all supported rates, rather than a large universal gain.

## Quality limits and readiness

This is a report-local research implementation, not a production pipeline
change. The FP32 guard is an empirically qualified engineering guard, not a
formal universal error bound. The static CZT cache assumes serial execution.

The independent saved-IQ numerical test evaluates 32 searches across all four
rates with host float FFTW. It retains every FP64 winner and measures a maximum
normalized score error of 3.779e-8. The C numerical unit test also passes on ARM;
expanded host unit/integration tests cover actual template sizes, zero energies,
irregular-grid fallback, and a constructed near tie, with normal and sanitizer
builds. Test-only revisions do not change the qualified executable sources.

The raw original-oracle ARM probe harness exits nonzero for inherited FP32
coarse discrepancies. Those receipts remain unchanged; paired checks establish
the actual effect of CZT, rather than relabeling the raw oracle result as a pass.

**The real-time/40%-headroom goal is not met.** At 34.332 CPU seconds per 0.120 s
of dual-RX data, the current full-inventory search needs about **286×** the
continuous single-core budget, or **477×** a 60%-CPU analysis budget. Concurrent
capture has not been demonstrated with this full GLRT workload.
