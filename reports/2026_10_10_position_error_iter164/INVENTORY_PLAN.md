# Full-193 single-pass discovery: input and cost feasibility

Source/metadata preparation only. No recording store, orbit propagation,
objective or optimizer was called. This is the iteration 151 **single-pass**
diagnostic expanded to the existing 193-member inventory, not parity with the
deployed multiseparation B7 pipeline. It preserves the 0.4 km goal without
claiming that discovery alone will achieve it.

## Authority and available clean bindings

The [107 protocol](../2026_10_09_position_error_iter107/protocol.json) is the
membership authority: DS16 63, DS17 51, DS18 34, and 45 previously consumed
POST18 members. Preserve DS16's additional 15 beyond its earlier 48-member
subset, the DS18 exposure labels and all newer-member identities. No quality,
analysis-readiness or endpoint-success filter should select members. Closed
reserves and the separate newer-22 inventory are outside this scope.

The 107 member schema is heterogeneous: the 148 historical members contain a
top-level `model_identity`, while newer members place source identities under
`sources`. Do not extend 151's historical-only projection by assuming identical
shapes across all 193.

The lean solution is the already prepared
[137 parity-bindings.json](../2026_10_10_position_error_iter137/parity-bindings.json).
A metadata-only check found exactly 193 entries with the required model
identities and all five physical input signatures. All 193 sanitized document
paths exist and match their recorded SHA256. Counts are 63/51/34/45, with no
missing documents or document hash mismatches. This checks persisted authority
availability, not current recording-read or model readiness.

Construct each research input binding from an explicit whitelist:

- label, session and original membership/exposure metadata;
- `model_identity` and `expected_input_binding`;
- sanitized `document_path` and `document_sha256`;
- the reviewed backend loader path/hash needed by 116's `make_loader`.

Exclude 137's `selected_path` and `selected_sha256`: discovery needs no saved
position or endpoint. In particular, do not gate membership on a selected
endpoint's qualification. The document projector
[137/prepare_parity.py](../2026_10_10_position_error_iter137/prepare_parity.py)
uses [131's inference whitelist](../2026_10_09_position_error_iter131/inference_loader.py),
which excludes reference coordinates and geographic errors. Whole historical
reference-bearing documents remain preparation provenance, not inference
admission inputs. Later reference evaluation must be separately sealed/gated.

At runtime, use 116 `make_loader` only to obtain the established backend ports,
then `131.InferenceLoader` uniformly across all members. Its clean path loads
public tracking metadata, verifies original observation order/content, selects
the causal TLE snapshot with the existing 505-second cutoff, constructs the
ordinary regional bank and checks all five physical signatures. It does not
call the historical backend `load_case` or import reference-based starts.
Any unavailable input, binding mismatch or runtime failure must produce an
explicit member/phase failure with the original denominator intact.

## Exact inherited work limits

Keep [151's policy](../2026_10_10_position_error_iter151/ports.py), including its
unchanged [150 promotion](../2026_10_10_position_error_iter150/transition.py).
Do not add 154 own-arm repair, 163 seed selection, a fixed common satellite
bank, or a policy selected from reference error.

| Stage | Inherited limit or rule |
|---|---|
| Discovery | Two independent native-score queues: fitted-c and zero-c; at most 400 points each; 40/20/10/5 km hierarchy and unchanged edge priority |
| Point work | Ordinary bootstrap up to 5 seconds; coarse fit up to 5 seconds / 200 iterations; shared bootstrap only at identical coordinates, fits keyed by actual arm |
| Search envelope | At most six checkpointed slices of 500 seconds, with 3000 seconds accumulated search allowance per member across both queues |
| Retention | Three regions per queue, 12.5 km minimum separation; downstream local radius 25 km |
| Arm transition | Own-arm audit first; when qualified zero-c state needs promotion, existing fixed-position fitted-c fit up to 5 seconds / 200 iterations; optional existing polish up to two rounds / 100 evaluations |
| Calibration | Existing recovery stage reservation 90 seconds; underlying fresh corrected postfit 20 seconds / 600 iterations, with unchanged qualification path |
| Association | Existing 60-second reservation and association limit |
| Regional finals | Existing start inventory and both final c arms, each fit 20 seconds / 600 iterations |
| Joint B7 | Existing B3/B4/B4W/B5/C6/B7 stage sequence and qualification; each attempted arm/stage up to 90 seconds / 600 iterations |
| Continuation envelope | At most two 500-second slices for each discovery branch |
| Concurrency | At most two single-thread workers; immutable source/runtime and exclusive claims; no silent orphan retry |

The phase envelopes constrain actual admission; adding individual stage limits
does not grant extra time beyond them. Deadlines are soft between operations,
and existing reconstruction/stage overruns must be measured, not described as
a strict wall-clock guarantee. Search failures explicitly block that member's
continuation rather than receiving an invented fallback endpoint. Sources:
[129/search.py](../2026_10_09_position_error_iter129/search.py),
[129/continuation.py](../2026_10_09_position_error_iter129/continuation.py),
[116/adapter.py](../2026_10_09_position_error_iter116/adapter.py),
[105/run.py](../2026_10_09_position_error_iter105/run.py), and
[production B7](../../src/leo/application/hard60_b7.py).

## Cost projection, not a runtime promise

The published [151 invocation-time table](../2026_10_10_position_error_iter151/RESULTS.md)
sums to approximately **11,842.5 seconds** for 12 members, or 986.9 seconds per
member. A simple linear projection is **52.9 worker-hours** for 193 members,
about **26.5 hours at ideal two-worker utilization**. The declared envelope is
5000 seconds/member: 3000 search plus 1000 for each continuation branch, or
**268.1 worker-hours** across 193 before soft overruns. These figures are not
an embedded-performance estimate or a guaranteed completion time. The pilot
included documented host I/O contention, and the newer 45 may differ in cost.

This is therefore substantial sustained work, even with existing IQ and no new
RF. A separate launch decision should acknowledge the cost and retain bounded
per-member checkpoints. If staging execution, freeze all 193 membership and
policy first and use a fixed metadata order; do not promote only promising
early cases or substitute partial-cohort metrics for the complete comparison.

## Reuse assessment

**Default: fresh numerical work.** The 151 policy explicitly set historical
point import OFF. Its twelve results cannot be treated as runtime-identical
controls simply because the successor repeats the conceptual policy.
[151's environment audit](../2026_10_10_position_error_iter151/ENVIRONMENT_AUDIT.md)
documents one shard launched through a mutable interpreter alias pointing to a
different release. Observed numerical libraries matched, but that is not proof
of identical whole-runtime execution. Importing any work requires an explicit
reviewed exception, exact source and physical state identity, arm-specific fit
keys, ordinary seed/bank/observation parity, and complete native trace replay.
It must carry historical cost separately and preserve original failures. Do
not overwrite old protocol digests or silently alias caches into a fresh run.

Iteration 150's one consumed DS18-022 result reused iteration 116 discovery and
performed a separately frozen continuation. It does not supply fresh matched
151-policy search for that member, so it should remain diagnostic evidence,
not a substituted full-cohort result. The same restriction applies to 107's
deployed-policy baselines: they provide clean input authority and historical
comparators, not automatically comparable single-pass numerical controls.

Thus the already verified **input projections** are reusable without a new
research framework; no numerical cache reuse is presently established. A full
comparison must report single-pass native versus zero-led per dataset and
pooled, both final c arms, missing endpoints, qualification, region availability,
frequency-fit effects and costs. It must not claim deployed-policy parity or
update the official full-cohort metric by splicing isolated recoveries.
