# Original-observation replay — proposed, not yet authorized for IQ reads

Use all 35,206 original selected observations in the frozen 110 random twelve,
with original receiver, visit, 20 ms start, fractional epoch, acquired CFO and
admission. No reacquisition, replacement, orbit selection, reference position,
position fit or accuracy claim. These are consumed development recordings.

Report refinement changes circularly modulo227272.7272727Hz, plus raw changes
and explicit wrap counts. Keep the frozen estimator representation: crossing
bin256 is not itself a large measurement error or grounds to choose a branch.

Use the original Python conditioned scorer for every member at both sample
rates. Require stored exact/control score parity within absolute 1e-10 and CFO
parity within 1e-6 Hz, then require the immutable 125 reconstructed spectrum's
winner/score parity. Only then emit both unchanged 125 refinements. Failures
remain explicit rows; do not tune tolerances or silently select another peak.
Original admission is unchanged. CFO differences are not errors relative to
truth; no real-corpus frequency-accuracy conclusion is available here.

The twelve metadata files and inventory are hash-bound, including full original
candidate identities. Capture manifest/rate/receiver order and visit counter and
count must match before using IQ. Runtime sources, immutable refiner, authority
and metadata form a conservative source closure. Public read-only storage
verifies compressed and decompressed chunk digests. No constructed storage paths.

One process executes one member serially. Parent allocates at most two global
numerical workers. Each member has a 1,200 s soft deadline checked before reads
and scorer calls; calls are not interrupted and elapsed can exceed the cap.
Remaining rows are budget-exhausted, never excluded. A raw visit cap is 32 MiB;
the public reader actually decompresses/caches a whole chunk, so a separate
64 MiB uncompressed chunk cap is enforced before any read (the storage contract's
maximum). These are not peak-RSS limits: compressed payload, old/new cached
chunks during replacement, decompression and Python correlation workspaces add
memory. Record elapsed time; peak memory is unavailable in this prototype.

Append-only launch claims, row JSONL and terminal receipts prevent silent retry.
A claimed member without terminal receipt requires explicit recovery review.
All original IDs appear once in normal terminal coverage, including parity,
input, capability and resource failures. A complete-with-failures result is
coverage, not successful parity. Persist raw results and both refinement changes;
do not promote a variant or substitute these measurements into positioning yet.

`freeze.py` only writes a metadata/source protocol; parent reviews and publishes
it before running `controller.py --labels LABEL ...`. No replay has run during
preparation. The earlier PREPARATION.md documents the initial design; this file
supersedes its outstanding-implementation and native-workspace descriptions.
