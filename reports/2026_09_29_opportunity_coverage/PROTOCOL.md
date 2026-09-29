# Observing-opportunity coverage pilot

Audit the first chronological recording in each immutable DS7/DS8/DS9 manifest,
chosen without scores. This three-record pilot checks the public export semantics
before scaling to all 258 recordings. It does not estimate geographic accuracy.

Load public TrackingInput and read-only AdaptiveHopIqStore inspection. Verify
capture manifest identities. Export each actual visit interval and each receiver
probe interval with RF and passing-candidate count. Compare the union of probe
sample intervals to the actual valid visit samples separately for each RX.
Check duplicate probe keys, cross-RX tuning/counter agreement, containment within
visits, input/timing qualification and missing visit coverage. Preserve unknown
or inconsistent cases; never turn them into target non-detections.

Distinguish zero passing extracted candidates from verified satellite absence.
Do not infer continuous observation between probe windows or satellite identity.
One worker, one record per process, timeout90s/AS4GiB/BLAS1/nice19. No IQ, RF,
propagation, provider request, fitting or production change. Preserve failures.
