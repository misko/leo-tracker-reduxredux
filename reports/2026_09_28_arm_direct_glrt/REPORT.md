# Direct GLRT after coarse or fine frequency search

These two approximate variants keep the full coarse search and all eight
candidate hypotheses in all 22 windows per dual-RX dwell. Coarse-direct supplies
the coarse CFO straight to final GLRT. Fine-direct retains the original fine
FFT and parabolic frequency interpolation, then supplies that frequency to
GLRT. Both skip the conditioned frequency screen and normalized verification.
Skipped scientific fields serialize as null, with explicit refinement-mode
metadata. Original verification-based ordering is not claimed.

## First 64 dwells, host

Both variants process 1,408 windows and 11,264 final candidate GLRTs.

| Method | Baseline hits recovered | Native positive hypotheses | Unmatched positive hypotheses |
| --- | ---: | ---: | ---: |
| Coarse-direct | 1,355/1,669 (81.19%) | 1,667 | 312 |
| Fine-direct | 1,354/1,669 (81.13%) | 1,670 | 316 |

At 2.5 MS/s these are 406/485 and 421/485 respectively. Neither result
establishes 90% individual-hit recovery. Matching remains one-to-one within
the same receiver/window at <=2 samples and <=8 kHz tracking CFO. Positive
totals alone are not recovery, and unmatched hypotheses are not automatically
classified as false positives.

Comparing identical coarse proposal identities with the preceding qualified
baseline explains the main failure. In each variant, 320 baseline-positive
proposal entries remain positive but shift tracking CFO by more than 8 kHz;
all those shifts lie within 8 kHz of one symbol rate (1/4.4 us, about 227 kHz).
Coarse-direct also turns nine baseline-positive proposal entries negative;
fine-direct turns none negative in this sample. This same-proposal diagnostic
is distinct from maximum-cardinality scientific hit matching. The final GLRT
residual spectrum does not, on its own, preserve the original frequency branch.
No retrospective frequency wrapping is used to inflate recovery.

## ARM fine-direct measurement

CPU0 on PLUTO+ 192.168.1.15 processes static saved IQ from RAM, without RF
collection or concurrent capture. Four 120 ms dual-RX dwells execute 88
overlapping 20 ms windows and 704 candidate GLRTs.

| Quantity | Full verification-fusion baseline | Fine-direct |
| --- | ---: | ---: |
| CPU seconds per dwell | 33.728123 | 24.454528 |
| Original hits recovered | 119/119 | 100/119 (84.03%) |
| Original positive windows with a recovered hit | 49/49 | 43/49 |
| Native positive hypotheses | 119 | 119 |

The speedup is **1.37922x**, or 27.5% less CPU time. Conditioned and
verification stage timings are zero; fine FFT costs about 3.82 s/dwell and
coarse search still costs 19.77 s/dwell. The 19 unmatched positive hypotheses
demonstrate why equal positive totals do not establish equivalent detections.
Coarse-direct has no ARM runtime claim in this experiment.
Restricting the completed host run to the exact four ARM cases also recovers
100/119 hits (matched-host-subset.json), supporting a method-dependent loss
rather than an ARM-only numerical discrepancy.

## Validation and scope

The completed 704-dwell host fine-direct run executes **15,488 windows** and
**123,904 candidate GLRTs**:

| Rate (MS/s) | Windows run | Individual hits recovered / original | Positive windows with recovered hit / original |
| ---: | ---: | ---: | ---: |
| 2.5 | 3,344 | 3,894 / 4,573 (85.15%) | 1,594 / 1,682 |
| 5 | 4,752 | 4,535 / 5,466 (82.97%) | 1,776 / 1,874 |
| 7.5 | 4,048 | 4,260 / 5,186 (82.14%) | 1,777 / 1,933 |
| 10 | 3,344 | 3,644 / 4,356 (83.65%) | 1,418 / 1,518 |
| **Total** | **15,488** | **16,333 / 19,581 (83.41%)** | **6,565 / 7,007** |

There are 19,578 native positive hypotheses, of which 3,245 do not match an
original positive under the stated gates. On the remaining 640 dwells after
excluding the initial selection set, recovery is 14,979/17,912 (83.63%).
Thus fine-direct clears 80% in every tested rate aggregate and in the ARM
sample, but does not meet 90%. These aggregate rates do not guarantee 80%
for every recording or future capture.

Across the full cohort, same-proposal diagnosis finds six formerly positive
entries become negative and 3,370 remain positive but shift by about one
symbol-rate alias. These are per-proposal diagnostics rather than the
one-to-one matched counts above. An alias-disambiguation stage may be useful,
but is not implemented or credited with recovery here.

Normal host and sanitizer tests cover all four rates, partial/full/zero input,
and exact equality with a separate final GLRT call at each candidate's actual
supplied CFO. Fine-direct's ARM unit passes the same checks. These tests prove
implementation consistency at that CFO, not equivalence to original refined
frequency. The full-control host64 run matches all 11,264 original candidate
objects after removing only the added refinement_skipped=false metadata.

Source-receipted coarse and fine host/ASAN/ARM builds are archived under
builds/. The top-level source is the later mode-selectable version; measured
binaries are tied to their individual archived receipts. Production analyzers
and frozen scientific fixtures are unchanged.

The larger fine-direct host704 run and its separate 640-dwell remainder are
reported in the completed audit files. It includes the 64 selection dwells;
the remainder excludes those exactly. The cohort is 0.361% of DS7, not full DS7.

This is still far from real time: 24.45 CPU seconds per 120 ms dwell is over
339 times the 72 ms budget needed for 40% headroom. Neither shortcut is an
exact replacement or a qualified simultaneous-capture deployment.
