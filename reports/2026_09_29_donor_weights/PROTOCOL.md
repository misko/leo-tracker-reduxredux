# Target-disjoint donor training weights

Existing full-dataset shared-scale fits use a different likelihood and include
target recordings. They are not reused as independent q020 donor calibration.
Use the same q020 trend-mixture likelihood, banks, masks and scales as the
eighteen target panels. Exclude all 72 distinct target recordings from donor
fitting. The remaining 186 scans form 25 chronological groups of at most eight,
split at dataset changes and every excluded-target gap. Preserve short groups.

Fit shared E/N plus one timing per donor recording from (0,0), (3,-3), (-3,3) km
with zero timings. Reuse the frozen profile-refinement optimizer and audit:
L-BFGS-B maxiter120,maxfun180,ftol1e-14,gtol1e-8,maxls30; E/N bounds ±12 km,
timing ±5s; success, boundary distance >=.001 and maximum gradient <=.01;
spatial finite differences .0005/.00025 km, timing .0000625/.00003125s;
each discrepancy and step disagreement <.002 and no timing-node crossing.
Select highest training score among fully audited starts. Model/evaluation
exceptions make that start explicitly unavailable with its traceback, not a
retry. A group with no qualified start supplies no donors. Process failures
stop the sequential launcher and leave remaining groups pending.

Export training candidate weights and signal responsibilities at the selected
point, with donor held scores as diagnostics only. Neither donor nor target
held outcomes select starts, groups or support. No reference error is used.
The original target q020 distributions remain unchanged. Map candidates through
the completed fourteen-roster catalogue mapping, never by bare row number.

For causal support, a donor group becomes available only after its latest
observation timestamp, not merely a donor scan's start: its fitted parameters
use the entire group. Count support from at least two distinct available donor
groups with signal responsibility × conditional candidate weight >=0.5 for
that candidate in at least one track per group. Report target conditional mass
supported, including zeros and unqualified groups. Also report one-group support
descriptively without promoting it. These are candidate-support diagnostics,
not verified identities, fitted residual corrections or geographic accuracy.

Three grouping tests plus the five existing optimizer/selection tests run
before source/input freezing. One sequential child per group, BLAS1/nice19,
timeout90s, AS4GiB, available memory >=5GiB. Retain every start and failure.
No new RF, raw IQ, propagation, archive/provider access or production changes.
Historical donor data budget is separate from four/eight target-scan budgets.
