# User-requested investigation: scan-fw-ac11ac00c0676d1b

Investigation in progress. The user explicitly requested root-cause analysis of
this scan's published failure. The fetched production B7 V3 result reports
55.685km fitted-c and53.945km c0 error; both final fits pass stationarity.

This is POST18-NEWER-20261009-051, in the previously assigned development group
group-380a90ad3f8c2c2c. Its outcome is now consumed for this user-directed
diagnostic. Preserve the immutable iteration89 mint and grouping; apply this
additional exposure record to subsequent reports. No reserve member is opened.

Known coordinates and error are evaluation-only. Recovery hypotheses must come
from the scan's ordinary retained regions and inference evidence. No reference-
guided seeds, satellite selection or operational winner selection is permitted.
No new RF collection or production changes are part of the investigation.

The highest-ranked ordinary retained region failed its calibration prefit
convergence check in all three regional-separation policies. That is a confirmed
upstream region loss, not yet proof that recovering it fixes the position error.
Next: inspect its persisted numerical state and the convergence failure, then
freeze a bounded matched-arm replay before any numerical recovery experiment.

## Prefit replay completed

The [four-prefit replay](PREFIT_RESULTS.md) reproduces immediate optimizer
termination above the unchanged stationarity threshold. Both ordinary-start
solvers remain unqualified; zero-timing restarts qualify but reach much worse
scores. No downstream position improvement has been established.

Two bounded receipts preserve a post-fit diagnostic type error. A separate
[terminal-audit supplement](prefit-terminal-supplement.json) proves that their
saved terminal vectors and objectives exactly equal the already-audited returned
states, so those audits can be reused without refitting or changing the original
receipts. Three regression tests cover mapping and typed terminal records.

Next is a separately frozen, small numerical refinement of the ordinary
unqualified state, followed by downstream matched-arm testing only if justified.
The published B7 position and production configuration remain unchanged.
