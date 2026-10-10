# All12 authorities and35,206 original selected observations recovered

Metadata-only projection is complete for the exact frozen110 random12 members:
**35,206/35,206** original positioning observations have full candidate metadata,
including acquired CFO, epoch, fractional offset, original scores, receiver and
probe start/count. No IQ reader, orbit prediction, numerical objective or
recording estimator was called. No member or window was replaced.

| Member | MS/s | Selected observations |
|---|---:|---:|
| DS16-020 | 2.5 | 3515 |
| DS16-024 | 10 | 3406 |
| DS16-054 | 10 | 3073 |
| DS16-058 | 10 | 2921 |
| DS17-006 | 10 | 2389 |
| DS17-015 | 10 | 3378 |
| DS17-027 | 2.5 | 2648 |
| DS17-031 | 10 | 3011 |
| DS18-013 | 2.5 | 2609 |
| DS18-023 | 2.5 | 2549 |
| DS18-024 | 10 | 2936 |
| DS18-029 | 10 | 2771 |

[inventory.json](inventory.json) binds each complete metadata file by SHA256,
exact110 membership authority, original input/analysis/evidence digests and
receiver counts. Each metadata file retains ordered window IDs and selected
candidate IDs, source-product/candidate digests, sample count, device origin,
rank-derived candidate identity and original fractional fields. It also binds
current exact/control template bytes at both rates/edges. Those current hashes
do not pretend to be a missing historical binary identity.

Metadata authority is verified against the unchanged, source-hashed historical
document. The compound evidence hash is reproduced exactly from original-window
metadata, causal TLE snapshot digest and ordered eligible catalogue IDs. Reading
and parsing this TLE metadata does not propagate or fit any orbit. This also
checks that current window preparation reproduces the source-bound original
selection. No reference coordinate/error contributes to selection or projection;
the hash-bound document is reference-bearing, but only identity/evidence/count
fields are used here.

The initial12 failed preparation receipts under `metadata/` remain preserved:
the first adapter mistakenly equated the window-only and compound evidence
hashes. Corrected `metadata-v2/` gives11 complete members; its S14 failure
reflects a missing redundant standalone snapshot field in the old report.
`metadata-v3/DS16-020.json` verifies the full compound digest successfully and
completes coverage. Inventory explicitly names which receipt is authoritative;
failed attempts are not overwritten or silently treated as successes.

Maximum raw visit allocation is2.4MB at2.5MS/s and9.6MB at10MS/s, both below
the proposed32MiB cap. Extra converted-probe and scorer workspaces remain outside
that raw-byte cap and require measurement. Both receivers are covered. Metadata
shows the recorded support epoch/sample windows, not an invented one-frame
restriction: the immutable candidate contract permits an epoch within its
20ms probe. The adapter now checks that actual probe bound.

The original products use the adaptive Python conditioned/fractional analysis
path; [CAPABILITY.md](CAPABILITY.md) documents it separately from the
research native oracle's2.5/5MS/s guard. The prepared callback can explicitly
use that original Python baseline, verify original exact/control/CFO and
autocorrelation winner parity, then apply unchanged125 refinements. It does
not silently fall back after a native error. Real-product parity remains
**unmeasured**, and historical implementation identity cannot be inferred from
an analyzer name alone. The proposed recording replay must freeze its explicit
scorer policy and source hashes before execution.

All12 metadata bindings name
`adaptive-hop-variable-dwell-fractional-glrt64-cfo-v1`. Additionally11,638
selected candidates have acquired CFO outside the research native diagnostic's
±400kHz limit. These are not invalid original measurements: the Python
conditioned scorer accepts their recorded finite CFO. Thus simply applying
the125 research native oracle to every row would also reject valid frequency
configurations, even apart from10MS/s. The proposed original-Python baseline
path must be explicit for the whole panel, with no CFO clipping or reacquisition.

Ten component/synthetic test cases cover membership, metadata identity joins,
missing-candidate coverage, original anchors, resource/unsupported guards,
per-window/read failures without duplicate IDs, and2.5/10MS/s scorer/refinement
geometry. Synthetic10MS/s tests explicitly record research-native rejection
and validate the original Python path. No actual recording correction or
position improvement is claimed. No IQ replay is authorized by this report.
