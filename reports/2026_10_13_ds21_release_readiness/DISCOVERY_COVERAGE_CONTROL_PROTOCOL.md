# Reference-blind discovery coverage control

This prespecified control changes only the discovery grid levels from
`[100, 50, 25, 12.5]` to `[50, 25, 12.5]` km, retaining the original 100-point
budget and all-band search priority. The aligned 50 km lattice has 80 initial
centers inside the unchanged 250 km regional prior, leaving at most 20 points
for the original score-prioritized refinement. It does not guarantee complete
coverage by 25 km local disks or global optimization.

The motivation is the sealed DS21-013 coverage failure: all six original local
search disks exclude the configured reference. That post-seal finding does not
define new grid points or select this control's proposals. The new lattice uses
the original `hierarchical_search` alignment and nearest-edge priority; no
reference coordinates enter freezing, training preparation, discovery or selection.

The new namespace uses `tools/ds21_discovery_coverage.py`. It binds the completed
original discovery, original case/source/input and census authority, unchanged
partition and clock nodes, original prior, causal TLE provenance and the original
full regional bank bytes. It reuses that full bank rather than the 49-candidate
DS21-013 downstream pool. Original failures, numerical sources and contracts
remain intact. A separate source archive binds this control and its qualified
ports, including its post-seal evaluator.

Every geographical point uses the unchanged `discover_channel_groups` ports:
the original three training views, five-second bootstrap budgets, per-point
candidate union, fitted c, physical priors, five-second/200-iteration fixed-position
fits and original low/high/all three-proposal selection with 12.5 km separation.
Failures and nonstationary results remain in durable point receipts. No new
observation, candidate identity, calibration term or held prediction is introduced.

One explicitly numbered invocation is bounded to 480 seconds internally,
495 seconds before TERM and 500 before KILL, including training preparation and
validation. Runs use one science process and one BLAS thread. There is no automatic
continuation or retry: failed/orphan slice and point claims block future work.
An intact checkpoint may continue only through a separately explicit numbered
invocation, retaining the same total 100-point budget and all previous point receipts.

The control validates source/parent authority before and after numerical work.
It replays the original pure hierarchy with the new levels and the unchanged
training selector, then seals every point binding and the selected proposals.
Cached results require the completed slice termination, intact source archives
and all point launch/termination receipts. Re-freezing cannot repair a deleted
immutable archive.

Only after that complete seal may `evaluate` join configured-reference errors
to the already selected discovery proposal locations. Those errors describe
discovery proposals, not final A/B/C fits or a full-DS21 accuracy result. Coverage
and frequency-fit diagnostics remain separate from position errors; no proposal
or model is selected by reference error. No held or locked inference is authorized.

The intended CLI is `freeze --directory <new namespace> --parent-discovery
<original completed discovery>`, followed by `run --directory <new namespace>
--slice-id 0 --maximum-seconds 480`. Root owns the actual freeze/run and optional
post-seal evaluation. No dataset execution has occurred during implementation.
Any downstream six-proposal/A/B/C comparison needs a qualified new parent adapter
and a separately authorized protocol; the present control is discovery only.
