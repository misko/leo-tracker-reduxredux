# Host 704 paired audit

The completed FFT coarse integration cohort at `host704-v1` matches the
conditioned-CZT oracle at `reports/2026_09_28_arm_conditioned_czt/host704-v2`
on every emitted candidate object.  The comparison used receiver/probe keys
and exact candidate-object equality, not only hit matching.

| Rate (Hz) | Dwells | Windows | Candidates | Positive windows | Positive hits | Object mismatches |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2,500,000 | 152 | 3,344 | 26,752 | 1,682 | 4,573 | 0 |
| 5,000,000 | 216 | 4,752 | 38,016 | 1,874 | 5,466 | 0 |
| 7,500,000 | 184 | 4,048 | 32,384 | 1,933 | 5,186 | 0 |
| 10,000,000 | 152 | 3,344 | 26,752 | 1,518 | 4,356 | 0 |
| Total | 704 | 15,488 | 123,904 | 7,007 | 19,581 | 0 |

Positive means `margin >= 0.025`.  All 19,581 original-baseline positive hits
were recovered and no positive hit was added.  The FFT run recorded zero
direct-fallback windows and 272,122 direct-repaired epochs.

The inherited original-baseline difference remains one 7.5-MS/s low-margin
window: ordinal 306, `scan-fw-43e84176a367910b` visit 693, receiver 0, probe
3, with four ordered candidate differences and no margin-gate crossing.  The
conditioned-CZT oracle has that same difference from the older baseline, while
the FFT result matches the oracle exactly; it is not attributable to the FFT
proposal.

Machine-readable counts, hashes, and attribution are in `paired-audit.json`.
This is an empirical host cohort result, not a formal floating-point
equivalence proof or an end-to-end performance claim.
