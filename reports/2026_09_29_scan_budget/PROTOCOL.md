# Scan-count curve over the same24-scan time span

Freeze membership before location outcomes. Reuse exactly the24 scans per DS
from time_balanced_scans. Chronological ranks define sets: N8 uses rank mod3
(three disjoint groups); N12 uses rank mod2 (two disjoint groups); N16 uses the
complement of each N8 group (three overlapping groups); N24 uses all scans.
Each set spans early/middle/late windows. No labels, geographic errors, or signal
quality select membership. Reuse verified six-start N8 results unchanged.

New N12/N16/N24 fits use the unchanged q020 model and six starts: E=-2,0,2km,
N=0 with either zero times or each scan's training-only41-node timing-grid
maximum at that position. All measurements/masks and bounds remain unchanged.
Max100 iterations/160 evaluations per start. Require optimizer success, no
boundary, max gradient<=0.01. Audit candidate optima in descending training
score order with finite differences; select the first with discrepancy<=0.02.
This avoids auditing discarded lower-score starts without weakening the final
endpoint gate. Targeted per-set cap180seconds, three workers maximum.

Report all sets, failures, median errors, sub-km counts and start-to-start elapsed
spans. Geographic reference is accessed only by post-fit summaries. Held data
remain the original interleaved masks. At N16 every scan occurs twice; report
half the summed held score so each observation has equal total weight across
budgets. This is a coverage-normalized predictive log-score summary, not a new
joint likelihood or independent-trial significance test. N24 has only one result
per dataset; do not present it as a robust median across independent sets.

No RF collection, new infrastructure, production changes, or remote publication.
