# Exact source-holdout screen: stopped at numerical qualification

The frozen eight-scan comparison did not reach geographic evaluation. Index 0
reproduces the completed pilot: all 56 cached folds qualify and the common
held-score selector chooses Student-t4/200. Index 4 completes all 44 new fits,
but one fails the required optimizer-success check. Consequently no family is
selected for index 4, and indices 8, 12, 16, 20, 24 and 28 are not attempted.
The denominator remains eight scans: one selectable, one unselectable and six
not attempted after the declared stop. No reference-position errors are read
or scored by this screen, and no positioning improvement is claimed.

The failed fold is Student-t8/100 with physical NORAD 65855 omitted (eight
tracks across the source). L-BFGS-B returns `ABNORMAL:` and `success=false`.
Its endpoint is interior, maximum absolute gradient is 3.5714e-5, and the
finite-difference gradient discrepancy is 1.9392e-6. Those small gradients do
not override the frozen success requirement. There is no retry, alternative
start, dropped fold or post-hoc acceptance. This is an execution/qualification
failure, not evidence that the statistical family worsens geographic accuracy.

All 44 processes exit normally; 43 fits qualify. Individual wall times are
6.12–17.63 seconds, totaling 413.53 worker-seconds at at most three concurrent
single-thread workers. Each fit had a 90-second cap. No later scan is launched.

The [protocol](PROTOCOL.md) fixes complete satellite-source deletion, original
training-only memberships, unchanged full-scan source weights, one full-data
endpoint initializer, and a common Student-t4/100 held scorer. Candidate
mixtures remain complete. Association labels and initializers come from the
full scan, so this is a conditional local diagnostic, not blind satellite
identification or a global-optimum guarantee. Inputs use the original causal
orbit banks; later orbit updates are not used.

The [preparation record](PREPARATION.md) documents preserved engineering
failures and the verified transitive provenance correction. Nine component
tests pass. The sealed plan binds 198 sources and declares 448 folds, of which
64 are validated cached fits and 384 were initially pending. The index-16
cached fits remain available evidence, but do not constitute an attempted or
selectable index-16 screen result.

Machine-readable evidence: [plan](plan.json), [index-0 selection](selections/00.json),
[index-4 failure assessment](selections/04.json), and [full-denominator outcome](outcome.json).
Any future optimizer revision must be a separate declared experiment; this
screen's failed attempt must remain visible.
