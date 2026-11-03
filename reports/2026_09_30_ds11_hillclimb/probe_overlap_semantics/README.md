# Shared probes are not equivalent to duplicated detections

The earlier28% figure counts training rows whose **raw probe** is shared with
another exported track. It does not establish that28% of training detections
are duplicates or mutually exclusive satellite observations. The distinction
changes the interpretation of the failed source-disjoint selector and the next
modeling priority.

The deployed [projection definitions](runtime_definitions.json) hash capture,
visit, receiver and probe into `source_group_id`. A candidate ID additionally
includes candidate rank and the analysis manifest. Thus distinct detections
within one20ms receiver probe share a source group by construction. They may
represent distinct signals, alternative explanations or detector artifacts;
these identifiers alone do not decide which.

Across the same eight DS11 screen scans:

| Quantity | Count |
|---|---:|
|Exported tracks / training rows|489 /16016|
|Shared training probe groups|2221|
|Training rows in shared probes|4487 (28.0%)|
|Shared groups containing different candidate IDs|2215|
|Exact candidate-ID reuse groups|6|
|Training rows in exact candidate-ID reuse|12 (0.075%)|
|Exact candidate IDs reused across training and held masks|0|
|Track-pair overlap edges|171|
|Overlap edges with identical training-group sets|0|
|Strict-subset overlap edges|15|
|Largest connected overlap component|5 tracks|

Among2311 pairwise shared-probe comparisons, the median native-frequency
separation, wrapped by the1/4.4microsecond ambiguity interval, is73.252kHz.
Only six pairs have wrapped separation below1Hz; these are the exact candidate
reuse cases. Their timestamps are identical and their unwrapped differences
are zero or integer multiples of the ambiguity interval. The median support-
center separation across all shared-probe pairs is106.075microseconds.
These separations distinguish the exported measurements; they do not prove
independent physical signals or rule out sidelobes, harmonics or common noise.

Consequences for modeling:

- A one-track-per-probe constraint may suppress real simultaneous signals.
  The failed greedy selector is evidence against that particular estimator,
  not proof that removing genuine duplicate detections hurts positioning.
- Exact candidate reuse is real but sparse in this screen. It cannot be
  equated to all4487 rows sharing raw probes. No position gain from removing
  the twelve reused rows has been tested or assumed.
- Entire overlapping tracks do not have identical observation support.
  Simply applying a log-sum-exp to their track scores would compare different
  datasets; unexplained detections still need a likelihood under each branch.
- Components have at most five tracks, so local combinatorics are manageable.
  The unresolved issue is the observation model: coexistence versus alternatives,
  detector selection and unexplained candidates, with shared IQ dependence.

The next bounded evidence check should test whether two different candidates
in the same selected probe retain separately supported pilot evidence when
modeled jointly. Choose probes from metadata before opening saved IQ and include
both candidates and background/control explanations. A mere second local peak
or high marginal score is insufficient to justify either independence or hard
exclusivity. Do not run a geographic exclusivity model solely from group IDs.

The [full census](outcome.json) binds the original input plan, diagnostics,
sidecar and each observation export. It verifies observation hashes, complete
track membership, per-point partition alignment, and shared receiver/RF keys.
Every exact reuse and partial-overlap component is retained for inspection.
A component test checks partial-overlap connectivity without equal-support
assumptions. The census and test exit0; no IQ reads, position fits, reference
errors, orbit updates or production changes occur.
