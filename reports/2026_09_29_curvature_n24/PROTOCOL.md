# Fixed-curvature N24 fits with unchanged outside-pool targets

Use the exact DS7/DS8/DS9 N24 pools and qualified baseline positions from
scan_budget. Warm-start one curvature fit per dataset at its baseline. Keep
the 0.1 Hz/s² truncated Gaussian prior and source-only grouping/basis rules
from shared_curvature; no width tuning, pool selection or new target selection.

Use the original out_of_pool five timestamp-selected targets per dataset.
At each new location integrate complete-scan q020 likelihood over uniform
[-5,+5] s timing. Compare with the sealed baseline N24, configured-center and
equal N8-mixture scores. No target location, timing or curvature fit. This is
a common-model location-transfer test, not a full new-model predictive test.

Inherited optimizer/boundary/gradient/derivative gates apply. Audit curvature
integration at 128/256 nodes to 0.01. Target timing scalar replay <1e-7 and
16/32-node discrepancy <=0.01, refining only failed integrals to 64/128 while
preserving originals. Keep failures visible; no parameter changes or restarts
based on results. Three dataset subprocesses, each capped at 180 seconds.

Geographic errors use the exposed unsurveyed reference; center-only error is
already about 809 m. Pools span 8–13 hours. Existing conditional candidate banks
and previously explored targets are not blind validation. No RF or production
changes. Retain source held scores but judge them alongside outside prediction.
