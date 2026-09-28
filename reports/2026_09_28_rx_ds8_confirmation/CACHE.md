# DS8 confirmation cache audit

The public-contract cache packaging passed an independent metadata-only audit for the four
preselected DS8 recordings. The set contains one recording at each supported sample rate
(2.5, 5, 7.5, and 10 Msps). Cache byte hashes, public input and analysis hashes, capture
bounds, qualification flags, pose revision and binding digests, and evaluation splits all
match the sealed readiness and prepared manifests.

The caches contain 17,728 probes arranged as 8,864 complete RX0/RX1 probe pairs. Probe
identity is unique by `(visit_index, probe_index, receiver_id)`, and each pair agrees on
start time, channel, edge, counter, and actual RF. The audit did not inspect candidate
measurements or outcomes.

The independent grouped-partition check accounts for all 8,864 opportunity windows and
8,864 groups: 5,312 train, 1,773 reception, 1,778 held-frequency, and one boundary embargo
window. Every group has one role, and an independent half-open interval sweep found zero
cross-role overlaps among 39,554 candidate source-support metadata rows.

Cache packaging took 7.21 seconds and 258,548 KiB maximum RSS. The 16-start full-model fit
took 37.94 seconds and 138,244 KiB maximum RSS. Both receipts report exit status zero.

Machine-readable details and bound input hashes are in `cache-audit.json`; the reproducible
read-only audit entry point is `cache-audit.py`.
