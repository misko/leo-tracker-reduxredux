# Conditional residual-slope transfer from independent donors

Diagnostic only: candidate cases are selected by training signal × candidate weight ≥0.5 and adequate training span. Slopes and eligibility use no target held data. These errors are not normalized predictive likelihoods or geographic errors.

| Target panel | Matched cases | Baseline held median abs (Hz) | Candidate slope | RX/RF control | Candidate beats baseline | Candidate beats control |
|---|---:|---:|---:|---:|---:|---:|
| DS7_early_8 | 0 | — | — | — | 0/0 | 0/0 |
| DS7_middle_8 | 0 | — | — | — | 0/0 | 0/0 |
| DS7_late_8 | 0 | — | — | — | 0/0 | 0/0 |
| DS8_early_8 | 0 | — | — | — | 0/0 | 0/0 |
| DS8_middle_8 | 0 | — | — | — | 0/0 | 0/0 |
| DS8_late_8 | 0 | — | — | — | 0/0 | 0/0 |
| DS9_early_8 | 0 | — | — | — | 0/0 | 0/0 |
| DS9_middle_8 | 2 | 148.800 | 146.062 | 147.195 | 1/2 | 1/2 |
| DS9_late_8 | 0 | — | — | — | 0/0 | 0/0 |

Zero matched cases mean unavailable evidence, not successful prediction. All 4,328 target tracks remain in coverage denominators; the table describes only the explicitly matched cases. Per-track medians are aggregated equally, and tracks/receivers within recordings are dependent.

![Matched conditional residual forecast errors](transfer.png)

[Protocol](PROTOCOL.md), [all eligibility and outcomes](summary.json), [tests](tests.log), [evidence hashes](evidence-sha256.json).
