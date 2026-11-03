# Screen plan preparation

The first two plan-preparation attempts are preserved as engineering failures,
not scientific fit outcomes. V1 required every old cache result to list each
input artifact directly, although the completed IID family cache instead binds
the immutable baseline plan that declares those artifact digests. V2 proved
that artifact chain but still required model helpers directly from each cache;
the index-16 exact-audit caches bind those helpers through their immutable
phase-one result.

The final preparation validates both provenance forms explicitly. A cache must
bind the exact original plan, the plan must contain the same indexed scan entry,
and every declared artifact digest must match the live bytes. Direct dependency
hashes must match when present. For exact-audit caches, helper and model hashes
may be inherited only through the exact digest-bound phase-one result. Cache
identity, session, endpoint seed, physical-NORAD membership, observation
coverage, qualification, common scorer, and source-balanced weight preservation
remain mandatory.

Nine screen component tests passed before the final run. V3 completed in
12.03 seconds with one BLAS thread and emitted a plan containing 448 jobs:
64 validated caches and 384 pending atomic fits, with 198 dependency paths
bound by digest. The eligible-source counts for indices
0, 4, 8, 12, 16, 20, 24, and 28 are respectively 14, 11, 15, 14, 18, 14, 11,
and 15.

The successful plan hash is
00b145247c5f6737dddcdfac19cda5b5d975c4d4f83040b5c5623758e5dc2453.
The failed v1 and v2 sources, logs, and receipts remain in failed_prepare_v1/
and failed_prepare_v2/. Preparation used no reference coordinate, launched no
position fits, and supports no geographic performance claim.
