# Original DS22 objective profiles

The unchanged B/C objectives were replayed at their sealed own-view training
winners for 001 and 003, four evaluations per model/view: 24 objective calls
per recording, zero optimizer calls. Every objective matched its saved value
within 1e-7. Original source/input authority and terminal bindings were checked
before and after. No reference or held data were used.

| Case | B all mean ms | C all mean ms | C all likelihood fraction |
| --- | ---: | ---: | ---: |
| 001 | 8.47 | 57.78 | 83.6% |
| 003 | 7.10 | 35.11 | 81.0% |

These are instrumented timings under concurrent host load, not isolated
benchmarks or speedup claims. Profiles nevertheless localize the dominant C
cost to likelihood evaluation. On 001, four C-all likelihood calls consumed
0.19294 seconds of 0.23091 total objective seconds; orbit prediction consumed
0.02157 seconds. The equivalent numbers for 003 are 0.11362/0.14030 seconds.

The actual original 18-call C matrices used 270.64/224.67 fit seconds for
001/003, versus B's 48.42/47.01. C-001 and C-003 contain rejected lower-objective
attempts, so acceleration of unchanged mathematics is worth qualifying before
attributing every selected-result difference to the statistical model.
This does not establish that faster convergence improves position accuracy.

Profiling source is `tools/ds22_objective_profile.py`, commit `b39474c80`;
four component tests and Ruff passed. Source-bound receipts and ranked
function profiles are in `local/ds22-objective-profile-v1/DS22-{001,003}`.
Both runs completed (35.404/32.760 seconds including training reconstruction).

A new private singleton likelihood prototype preserves normalized native
branch weights, visibility, fixed clutter/signal mass, circular residuals,
calibration and orbital timing. It uses positive densities with a guarded
fallback to the original log-domain evaluator. Seven component tests pass;
real-recording objective/gradient/posterior equivalence and timing qualification
remain required before any new fitted comparison. Existing scientific sources
and receipts are unchanged.
