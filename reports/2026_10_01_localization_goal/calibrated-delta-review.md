# Exact proposal reuse improves speed and acceptance, not geographic accuracy

Replacing only the changed track's prediction terms avoids rebuilding unrelated
candidate predictions. The92alternative audit matches full scalar and vectorized
objectives within4.71e-12. Including cache setup, that proposal workload is5.22×
faster. It covers8clutter-to-satellite changes,34satellite-to-clutter changes,
70changes with a shared old satellite identity,14nonzero epoch-prior profiles,
and92no-op checks. These are real-data equivalence checks, not speed estimates
for the whole localization pipeline.

When epoch profiling changes a nuisance value, the implementation recomputes
all training terms because clutter visibility may depend on those epochs.
Unchanged candidate predictions are reused only at the fixed cached state.
The cache is rebuilt after each continuous fit or accepted assignment change.

Fresh12-scan fits use the same parents, objective, proposal ordering, maximum
12rounds and25-second total warm deadline as the preceding experiment. The
original failed receipts remain unchanged. Acceptance improves from10/12to11/12:
DS11-F018 completes in20.83seconds with1193.9m error. DS10-F028 still reaches the
deadline after8fits and308proposals and receives no accepted geographic score.

All22previously accepted control/candidate pairs reproduce exactly the same
states, assignments and tested-proposal order. The complete scalar final-round
alternative audit and finite-difference stationarity audit pass for all11new
accepted candidates;12controls also pass. Thus the optimization preserves the
existing successful search results rather than finding more accurate locations.

| Same11accepted scans | Median error (m) | p90 error (m) |
|---|---:|---:|
| Original all-data baseline | 1,860 | 2,997 |
| Calibrated fixed assignments | 1,923 | 3,576 |
| Calibrated alternating with reuse | 1,923 | 3,486 |

Conditional quantiles must not hide the remaining failure. Counts using all12
planned scans are3/12within1km and8/12within3km. Median warm runtime is8.40seconds,
maximum25.23seconds, and median CPU8.31seconds. These exclude acquisition,
preprocessing and the parent calibrated fit. Timing comparisons between runs
are not host-load controlled. No cold90-second, held-out or uncertainty claim.

Retain the verified computation improvement, but do not promote the localization
model or launch a64scan benchmark. Its accepted subset still underperforms the
original baseline. More search of this same objective is not supported as the
main route to improved accuracy.

Next, audit the per-track frequency-offset treatment. Candidate predictions use
a GLS offset estimated from the original eight training observations. The
candidate likelihood currently plugs that estimate in without propagating its
shared uncertainty across checking observations. Quantify the conditional offset
uncertainty and correlated checking residuals at sealed states before proposing
an integrated-offset likelihood. Distinguish this per-track statistical nuisance
from the previously rejected assumption of one shared receiver frequency offset.
Do not infer a physical oscillator fault or tune offset corrections against GPS.

Artifacts: `calibrated-delta-audit-v1.json`,
`calibrated-delta-search-v1-evaluation.json`,
`calibrated-delta-equivalence-v1.json`, raw receipts, freezes and SHA256 sidecars.
No RF collection, production replacement or new recording validation.
