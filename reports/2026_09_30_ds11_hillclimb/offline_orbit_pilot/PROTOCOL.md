# Offline archived-orbit diagnostic, separate from the causal goal

The user permits offline positioning only as a separately reported comparison.
Use the existing four-hour delayed-orbit inventory. Its cutoff is the archived
request timestamp, not a proven byte-publication deadline. Label every output
offline-only; no result from this experiment completes the primary causal goal.

Select the earliest two original-plan indices with at least one retained track's
training-MAP satellite (conditional confidence>=0.90 at the original IID
endpoint) whose inventoried replacement has a strictly newer element epoch.
Inspect scans in index order; no reference coordinates or errors enter selection.
Retain all candidate slots, measurements, masks, catalogue normalization and
track membership. Replace every inventoried changed candidate's position and
velocity states at the original timing nodes; preserve unchanged slots exactly.
Replay each replaced original element against the saved bank before accepting
its replacement. Hash the exact archive bytes and records. Report the epoch
advances, actual post-capture information and all fallbacks.

Use the existing Student-t4/100Hz likelihood and per-track CFO profiling with
original bounds. Compare original and offline states using the original IID
endpoint and the configured center with timing0 as two fixed starts. Select
highest qualified training score before geographic scoring; retain failures.
Qualification: optimizer success, interior margin>=.001, gradient<=.01 and
finite-difference discrepancy<=.02. No geography-based tuning. Report paired
errors, held Doppler prediction, identity changes and execution time for both
scans; isolated gains cannot establish a general accuracy improvement.

Each scientific child<=90seconds, at most three single-thread workers. Existing
archive/banks only; no RF collection. This is an orbit-quality diagnostic, not
permission to use later states in causal production positioning.
