# Joint orbit model: DS11 held-prediction bridge

At the original IID positions, the causal orbit arm beats both controls on
both preselected scans. The frozen advancement gate passes.

| Scan | Orbit minus zero (nats) | Orbit minus linear (nats) |
|---|---:|---:|
| 0 | 320.703 | 146.643 |
| 16 | 208.822 | 26.276 |

Every candidate/coefficient CFO is fitted using training observations only.
Held prediction uses the joint-minus-training log normalizer for shared
candidate/coefficient states, conditional on those plug-in CFO estimates.
All source groups and singleton tracks enter the totals. This bridges the
historical training-mean residual calculation to the actual profiled-CFO model;
it is not a fully CFO-integrated likelihood. Training scores replay the numerical
benchmark within 1e-6. Two synthetic tests pass for held isolation and zero
direction cancellation. Runtime was 10.55 seconds, with no position fits or
reference coordinates used in this test.

The historical priors remain frozen. These are exposed pilot scans and the
comparison is conditional on the original fitted positions and source groups.
Improved held prediction does not establish lower geographic error.

See [protocol](PROTOCOL.md), [complete results and source hashes](outcome.json),
and [bounded geographic pilot](../joint_orbit_position/PROTOCOL.md).
