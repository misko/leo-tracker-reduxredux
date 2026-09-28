# Input preparation for disjoint equal-sized validation panels

Use all45 sessions frozen in the published union-panel outside-union proposal:
15 per DS7/DS8/DS9, selected by capture timestamps after excluding every union
record. No substitution based on cache availability, fit outcome or geography.
These are outside the union, not certified research-blind recordings.

Reuse the15 existing DS7 native inputs after artifact-hash and loader checks;
archive their previously unpublished banks from the local cache. Export cached
frequency observations and unchanged corrected-DS6 causal five-anchor/top8-union
banks for the30 DS8/DS9 recordings. Use existing public read-only corpus/TLE
ports. No waveform/IQ reads, RF collection or provider fetch.

Bind dataset/capture manifests, sample rate, partition seed2026092711, eligible
track accounting, bank shapes/timing grid and provider snapshots collected before
capture start minus505s through the existing loader. For DS9 also verify the
minted GLRT metrics-manifest binding. Archive runtime versions and installed
public-reader source snapshots.

At most two input workers. Each worker handles a predetermined chronological
five-record batch with an1800s deadline. Per-stage caps: observations60s,
banks240s, validation30s; address space4GiB, BLAS1, nice19. There are three
batches per dataset, nine total. No automatic retries; retain every failure
and unstarted stage in the ledger. Do not fit or silently shrink an incomplete
15-record panel. Geographic fitting is a separate experiment after validation.
