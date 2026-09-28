# Host 704 paired audit

The revised host CZT result at `host704-v2` is exactly identical to the
scoped host reference at `/var/tmp/leo-host-coarse-scoped/cohort704` on all
123,904 emitted candidate objects, across 704 dwells and 15,488 receiver/probe
windows.  All 7,007 positive windows and all 19,581 positive hits from the
original baseline were recovered; the revised run added no positive hit.

| Rate (Hz) | Dwells | Windows | Candidates | Positive windows | Positive hits | Scoped-object mismatches |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2,500,000 | 152 | 3,344 | 26,752 | 1,682 | 4,573 | 0 |
| 5,000,000 | 216 | 4,752 | 38,016 | 1,874 | 5,466 | 0 |
| 7,500,000 | 184 | 4,048 | 32,384 | 1,933 | 5,186 | 0 |
| 10,000,000 | 152 | 3,344 | 26,752 | 1,518 | 4,356 | 0 |
| Total | 704 | 15,488 | 123,904 | 7,007 | 19,581 | 0 |

Positive means `margin >= 0.025`.  Hits use the existing two-sample epoch and
8 kHz tracking-CFO matching tolerances.  The audit compares all emitted
candidate fields, including coarse/refined epoch, CFOs, scores, and downstream
verification fields; it found no missing windows or candidate-object mismatch
against the scoped reference.

There is one ordered mismatch window with four candidates when compared with
the older original baseline: ordinal 306,
`scan-fw-43e84176a367910b` visit 693, receiver 0, probe 3, at 7.5 MS/s.  Its
ranks 1--4 are all below the positive margin gate.  The scoped reference has
the same four-object ordering difference, while revised CZT equals the scoped
reference exactly.  This attributes the difference to the inherited
low-margin FP32-coarse ordering divergence, not the CZT screen.

The machine-readable counts, comparison fields, and attribution are in
`paired-audit.json`.  This is a host cohort result and does not claim universal
floating-point equivalence.
