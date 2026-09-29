# Omit-power qualification

This is a saved-IQ qualification only. The ARM timing wrapper retains CPU0
affinity in the NEON proposal binary and performs no capture, RF, or GLRT work.
It uses four static dual-RX 2.5 MS/s dwells, three repetitions each, for 264
receiver-window rows. ARM top-four outputs exactly match the host omit-power
collector (zero mismatches).

| ARM proposal stage, per 22-window dwell | Current NEON/radix baseline | Omit power | Change |
| --- | ---: | ---: | ---: |
| Total | 729.167 ms | 570.501 ms | -158.666 ms (-21.760%) |

The current NEON/radix baseline is 729.166691 ms per dwell. The stage-only
omit-power timing is 194.175 ms fold/convert, 276.989 ms correlation, and
97.987 ms ranking, totaling 570.501 ms per dwell.

The full 704-dwell host evaluation applies the omitted-power top four with
radius 2 to the preferred final-reuse f2 raw-condition scorer. In
`evaluate.py`, `mean_timings_ms` sums the 22 receiver-window timings for each
dwell before dividing by the 704 dwell results: the figures below are **per
dwell**, not per window.

| Final-reuse search, per dwell | All-four radius-2 reference | Omit power | Change |
| --- | ---: | ---: | ---: |
| Total CPU | 83.651 ms | 82.890 ms | -0.762 ms (-0.911%) |

The exact standard-hit audit used 704 dwells, 15,488 windows, and 123,904
candidate entries. Omit power recovered 19,225 of 19,581 reference positive
hits (98.1819%), 24 fewer than the all-four reference's 19,249. It emitted
40,643 positive hits, of which 21,418 were unmatched; 356 reference positive
hits were not recovered.

| Rate (Hz) | Reference hits | Recovered | Missed | Unmatched native hits |
| ---: | ---: | ---: | ---: | ---: |
| 2,500,000 | 4,573 | 4,516 | 57 | 5,252 |
| 5,000,000 | 5,466 | 5,358 | 108 | 5,802 |
| 7,500,000 | 5,186 | 5,098 | 88 | 5,599 |
| 10,000,000 | 4,356 | 4,253 | 103 | 4,765 |
| Total | 19,581 | 19,225 | 356 | 21,418 |

Receipts: `arm4-omit-power-v1/summary.json`,
`host704-omit-power-v1/summary.json`, and
`../2026_09_29_arm_subsecond/wave2-omit-power-final-reuse-radius2/`.
