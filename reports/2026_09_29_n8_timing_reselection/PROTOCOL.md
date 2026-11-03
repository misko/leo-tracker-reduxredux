# Frozen timing re-selection on all nine contiguous eight-scan panels

Use all DS7/DS8/DS9 early/middle/late eight-scan panels and their existing
qualified six-start q020 endpoints. Apply exactly the previous one-round rule:
at fixed geography compare each current continuous timing with the 41-node
training grid; replace only for gain >1e-7, then jointly refit if any changed.
No additional rounds, reference selection or retry of failed endpoints.

Retain original endpoint unless the refit qualifies and improves source score
by >1e-6. For each such improvement evaluate BOTH old and new locations on all
five frozen outside-pool scans under original q020 with shared timing integrated.
No target score enters endpoint selection. Unchanged panels have no new target
computation. Save each source result before any target evaluation.

Three dataset workers, each handling its three panels, capped at 300 seconds.
Preserve source checkpoints and failures. These previously examined panels and
targets are exploratory, not a blind accuracy test. No RF or production changes.
