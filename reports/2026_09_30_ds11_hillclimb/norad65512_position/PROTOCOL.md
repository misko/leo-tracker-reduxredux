# Matched scan-0 waveform correction ablation

After the complete111-row measurement audit, carry **both** frozen pilot arms
into a position comparison. Do not select an arm using within-excerpt held
symbols, localization-held observations or geographic error. This is an
exposed-scan mechanism test, not a model-promotion or confirmation experiment.

Use the original scan-0 causal candidate bank, t4/100-Hz independent likelihood,
full candidate mixtures, CFO profiling, timing grid, altitude and search bounds.
For each arm, add its measured canonical correction at all111 exact training
rows. Do not filter weak measurements, smooth/interpolate corrections, alter
aliases, change observation timestamps or change any localization-held value.
All111 measurements have completed without a frequency-search-bound hit.

The unchanged control is the original qualified IID endpoint, accepted only
after source/receipt validation and exact score replay within1e-6nats. Check
fresh gradients and finite differences under the unchanged qualification rule.
Each corrected arm gets exactly four starts: the original IID endpoint and
generic `(E,N,tau)` starts `(-2,0,0)`, `(0,0,0)`, `(2,0,0)` in km,km,seconds.
Use the original L-BFGS-B options and qualification checks. Bound each start
to90seconds, use one BLAS thread, at most three concurrent workers, and retain
every failure. No retry or numerical recovery is included in this ablation.
Choose each arm's highest-training-score qualified endpoint. Require at least
one qualified endpoint in each arm before any geographic comparison.

Freeze all eight jobs and source bindings before fitting. At each terminal
endpoint report held likelihood using both the unchanged measurement model and
the corresponding corrected-training model. Neither score chooses an arm.
Only after both endpoints are sealed compare their position errors with the
cached control, using the original unsurveyed roof reference. Report both
arms and all eight attempted starts; do not call the better geographic result
a selected or validated policy. Any broader test requires a new protocol.
