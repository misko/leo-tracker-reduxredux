# One time offset per scan versus independent track offsets

## Scope and outcome

For the 2026-09-26 12:50 scan (`scan-fw-d86e8f23c0624bac`), a single shared time offset **narrowly reverses the score preference** between the known receiver location and the published incorrect Reno location. It does not improve absolute fit quality: both locations fit worse, and two long reference-location tracks fit much worse.

This is a **two-fixed-location diagnostic**, not an independent-prior geographic search or a demonstrated reduction of the 706.761 km Reno location error. No Sacramento coordinates/candidates are used. The reference location is an explicitly labelled diagnostic comparator, never a proposal fed to the Reno search. No observations from neighboring scans are combined.

## Controlled full-catalogue comparison

At each fixed location, every track can choose its own satellite from the original full catalogue and retain its own constant frequency offset. Compare:

- Independent timing: each track chooses its own satellite and tau on training observations.
- Shared timing: one tau must explain the entire scan, with satellite identity and constant frequency offset still fitted separately per track.

Both arms use the same -5 to +5 second grid in 1-second steps. Shared tau minimizes occupied-second-weighted training loss, capped at 800 Hz per track. All 46 tracks remain in the fixed denominator of 892 represented seconds. Identity and timing selection use training observations in both arms; the original evaluation observations are reported afterward. The reused partitions and selected failure are not independent validation.

| Timing model | Reference training RMS | Wrong Reno training RMS | Reference evaluation RMS | Wrong Reno evaluation RMS |
|---|---:|---:|---:|---:|
| Independent per track | 294.89 Hz | 180.07 Hz | 294.88 Hz | 201.52 Hz |
| One shared offset per scan | 472.99 Hz | 475.66 Hz | 483.19 Hz | 498.30 Hz |

The training-score advantage changes from 114.82 Hz in favor of wrong Reno to only 2.67 Hz in favor of reference. The evaluation-score advantage changes from 93.36 Hz in favor of wrong Reno to 15.11 Hz in favor of reference. These are raw score differences, not calibrated likelihood ratios or confidence levels.

The chosen scan offset is **-1 second at reference** and **-4 seconds at wrong Reno**. These are alternative location hypotheses, each allowed to estimate its own single scan offset; they are not two simultaneously fitted offsets for one hypothesis. Neither shared optimum lies at the search boundary.

Under shared timing, 7/46 reference identities and 26/46 wrong-Reno identities change relative to the training-only independent-timing arm. All tracks remain matched. Compared with the published/evaluation-selected identities, the changes are 10/46 and 24/46, respectively.

Uncapped evaluation RMS gives the same direction of preference: independent 348.95 Hz reference versus 201.52 Hz wrong Reno; shared 670.47 Hz reference versus 735.91 Hz wrong Reno. The shared fit has 7 reference tracks and 8 wrong-Reno tracks above the 800 Hz cap.

## Effect on the two longest tracks

Both reference fits retain satellite 63850 but must use the shared tau of -1 second:

| Track span | Reference independent evaluation RMS | Reference shared evaluation RMS |
|---|---:|---:|
| 51.72 s | 525.62 Hz | 1,385.25 Hz |
| 50.59 s | 474.21 Hz | 1,172.67 Hz |

Those tracks preferred -7/-8 seconds in the earlier widened diagnostic. A rigid scan-wide offset prevents those adjustments. At wrong Reno, the same tracks retain satellite 63780 and use tau -4; their shared evaluation RMS values are 196.12 and 130.72 Hz. Thus the shared-clock result does not repair these long-track association explanations: other tracks drive the relative location-score change.

## Fixed-identity sensitivity check

To isolate timing from satellite reassignment, use each branch's previously selected identities without changing them. This uses only that branch's own identities, not a cross-location association pool:

| Model, identities fixed | Reference evaluation RMS | Wrong Reno evaluation RMS |
|---|---:|---:|
| Independent tau, ±5 s | 293.47 Hz | 189.78 Hz |
| One scan tau, ±5 s | 500.17 Hz | 556.69 Hz |
| Independent tau, ±30 s | 241.05 Hz | 209.80 Hz |
| One scan tau, ±30 s | 500.17 Hz | 556.69 Hz |

With fixed identities, reference picks shared tau -1 s and wrong Reno picks +2 s, unchanged by widening to ±30 s. Allowing satellite reassignment changes wrong Reno's shared optimum to -4 s and reduces its disadvantage. **The full-catalogue shared model was tested only over ±5 s**; the ±30 s sensitivity does not establish its global optimum outside that range.

The original production identity rule uses evaluation RMS to choose identity after fitting tau on training. Its reproduced scores are 293.47 Hz reference and 189.78 Hz wrong Reno. The main table deliberately uses a training-only independent arm so that the comparison with shared timing does not conflate a clock change with identity-selection policy.

## Interpretation

One shared offset removes flexibility that the wrong location exploits. However, it also prevents reference-location tracks from absorbing satellite-specific orbit/model errors. The net effect favors the reference site only narrowly in the training objective, while worsening absolute fit. This is promising as a constraint to investigate, not evidence that all tracks physically share one identifiable timing error or that the Reno search now localizes correctly.

A clean location-error test would rerun the Reno search using only its own prior and independently generated geographic proposals, with the shared-clock policy fixed in advance. The reference coordinates must remain evaluation-only. Neither shared Sacramento/Reno proposals nor reference-seeded geographic refinement is justified by this experiment.

## Verification

- `compare_scan_clock.py` reconstructs the same evidence/TLE snapshot through public read-only ports and checks their digests.
- Legacy full-catalogue scores at both fixed sites reproduce the preceding saved results within 1e-6 Hz.
- `scan_clock_results.json` retains full selected identities, per-track tau/CFO/residuals, denominator, parity checks, and source/evidence bindings.
- 15 focused tests pass across the new comparison and existing numerical/audit suites, including shared tau with distinct track identities/CFO, occupied-second weighting, missing-evidence penalties, and isolation of evaluation observations from clock selection.
- No production code, search output, prior, public contract, or RF collection was changed.
