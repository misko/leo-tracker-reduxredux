# Causal catalogue propagation failures

All six failed case/identity entries in the four prior accepted-case catalogues have **SGP4 code 1 at all 381 knots** on the exact discovery grid, −40 through +340 seconds relative to each scan origin. Code 1 means propagated mean eccentricity is outside 0..1. Every position and velocity is nonfinite, so radius minima/maxima are unavailable; none is fabricated. This establishes invalid propagation of those element models, not physical satellite decay.

| Case | Failed identity | Code-1 knots | Nominal element age (h) |
|---|---:|---:|---:|
| DS26-0034 | 46174 | 381/381 | 50.657 |
| DS26-0044 | 46174 | 381/381 | 55.189 |
| DS26-0044 | 57416 | 381/381 | 19.469 |
| DS26-0066 | 46174 | 381/381 | 64.732 |
| DS26-0066 | 57416 | 381/381 | 29.012 |
| DS26-0251 | 48582 | 381/381 | 69.907 |

Fresh catalogs FRSH-0001 through FRSH-0005 have **zero failed identities**, out of 11,182 / 11,182 / 11,182 / 11,181 / 11,181 causal catalogue identities. No partial or unknown failure appears in any of the nine audits. All nominal epochs and archive collections satisfy their scan cutoff and 72-hour epoch rule; parsed epochs agree with ledger epochs to 1 ms.

The generic proposed eligibility rule in [propagation_audit.py](propagation_audit.py) uses no NORAD list, RF scores, or GPS. Every knot must have error zero and finite state to be eligible. A uniform documented model-invalid SGP4 code from 1/2/3/4/6 at **all** knots can receive an explicit `model_invalid` exclusion receipt; every actual exclusion here is code 1. Partial failures, mixed errors, unknown or obsolete codes, and nonfinite states without an error **block** the catalog rather than silently disappearing. Code 5 is obsolete and is not accepted as an exclusion reason. This is a proposed research input-universe rule, not a production change.

[propagation_audit.json](propagation_audit.json) retains the exact source hashes, element lines and hashes, parsed/ledger epoch, collection time, grid error sequence, documented library messages, finite-state counts, and null-radius reasons. The numerical path uses the same nanosecond rounding, Julian conversion, SGP4 array API, and all-knot usability mask as the unchanged `bank_for` helper. The 10.6-second audit performed no RF fitting or catalogue modification. Component tests cover complete, partial, mixed, unknown, obsolete, and nonfinite cases and verify all recorded failure coverage.
