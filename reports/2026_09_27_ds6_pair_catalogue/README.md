# Additional DS6 source-pair census

The metadata census is complete for ten inventory-ready scans outside the
preceding phase cohorts. It retains **12 eligible source pairs covering 250
distinct visits in five scans**. These are opportunities for extraction, not
250 recovered phase measurements. No IQ was replayed for this census.

| Recording | Eligible pairs | Distinct visits | Training visits | Held visits |
|---|---:|---:|---:|---:|
| scan-fw-2e6b78f0cd0cbbbc | 0 | 0 | 0 | 0 |
| scan-fw-60d9d1e77c14da0a | 0 | 0 | 0 | 0 |
| scan-fw-cd6a029d633dcc0e | 1 | 8 | 5 | 3 |
| scan-fw-abfbc40b880a90c1 | 0 | 0 | 0 | 0 |
| scan-fw-8f4f960d9db67798 | 3 | 61 | 38 | 23 |
| scan-fw-e84e2f55976c0a8c | 0 | 0 | 0 | 0 |
| scan-fw-1d767ca00c2eecb1 | 5 | 141 | 78 | 63 |
| scan-fw-9d7b6a0db558703a | 1 | 13 | 7 | 6 |
| scan-fw-887c0ec0eb44025b | 2 | 27 | 18 | 9 |
| scan-fw-127d8fc36e804ae2 | 0 | 0 | 0 | 0 |

`protocol.json` binds inventory membership, preceding cohort exclusions and
extraction dependencies. Each scan plan binds the protocol and source manifests.
Its `eligible_groups` field preserves every qualifying pair and visit recipe.
The inherited `selected` and `selected_groups` fields are provisional planner
outputs; they are not a completed curvature ranking or a new replay protocol.

Eligibility retains the earlier GLRT and positioning-track joins: support on
both receivers, distinct source candidates, fractional-margin checks, epoch
agreement, frequency separation and compatible differential offsets. Each pair
has at least two training and two held visits under seed 2026092711. See
`prepare.py` for the exact gates. Failing these gates does not establish that a
recording contains no useful signal.

The motivation is the preceding [geometry-versus-drift experiment](../2026_09_27_ds6_long_phase_geometry/README.md):
two training endpoints cannot distinguish a nearly linear geometric trend from
receiver response drift. The next selection needs an interior training visit
and sufficient predicted curvature, followed by independent held evaluation.
Curvature ranking, new IQ extraction and predictive evaluation are **pending**;
this report makes no additional accuracy claim.

Run `python3 test_census.py` for saved membership, partition, provenance and
summary checks. Run `sha256sum -c SHA256SUMS` for the published artifact seals.
Recreating plans requires the original read-only capture and tracking stores
and the scientific environment used by the preceding report planners.
