# Frozen tone-rescue validation

Validate the unchanged native_tone_rescue candidate on the 26 reserved
constructed cases from tg11_diagnostic/dataset/cases.json. Their membership,
seeds, physical truth and generator were fixed before candidate development.
Generate IQ into this new directory only; preserve the original golden manifest
and all prior source locks. Mark validation opened in every new generation and
evaluation receipt. Once generated, these cases are consumed validation and may
not be represented as unseen in later tuning.

Freeze this protocol, runner/tests, original candidate sources and binary,
generator sources, design and manifest before generation. Reconstruct metadata
without IQ first and require equality with the reserved truth: exact seeds,
membership and discrete fields; computed floating-point metadata within 1e-13
relative / 1e-12 absolute tolerance. Pre-generation tests found a 4e-14 amplitude
difference from numerical-library reduction order under one thread. On actual
generation record additional measured power/clipping data separately, hash each
NPY, and require zero clipping. One bounded generation (60 seconds), one bounded
evaluation (120 seconds), CPU0 and single-threaded numerical libraries. No RF,
QNAP mutation, production change, or original real holdout opening.

Compare full application, unchanged native tracking and unchanged tone-removal
rescue, with separate causal state, rotating method order and complete-call
CPU/wall timing. Reuse the existing scientific association rules, retaining
all pair inventories and physical truth results. Inputs remain immutable.
Per-call timing excludes file reading, hashing, initialization and serialization.

Qualification gates for this constructed split: all required negative policies
pass; no active output unassociated with injected truth; no truth-associated
primary positive is lost or changed by rescue; aggregate candidate CPU speedup
is at least 10x at each sample rate. Weak pilots and region-specific support
remain explicitly reported, not silently counted as passed detections. Report
reference disagreement separately because native and application score different
symbol regions. Report median/p95/max latency and calls above 120 ms; this
latency target is separate from 10x compute qualification. Small negative counts
cannot establish a rare false-alarm probability.

Any failed gate rejects this candidate on this split; do not repair parameters
in place. Successful constructed validation does not establish recorded holdout
retention or single-core real time. Those remain separate required evidence.
