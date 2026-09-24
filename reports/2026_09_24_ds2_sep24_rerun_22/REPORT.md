# DS2 September 24 successor: post-seal evaluation

This report evaluates the sealed DS2-22 inference products after completion. The reference coordinate was supplied only to the evaluator through its CLI; it is not an inference input and is not reproduced here.

## Dataset and admission

The successor manifest admits **22 sessions** in **3 cohorts**. It retains exactly **3 explicit geometry bindings**. Ordinary model families use all 22 admitted sessions under the sealed admission plan.

| Cohort | Radio | Sample rate | Sessions | Geometry sessions | Joint eligible |
| --- | --- | ---: | ---: | ---: | --- |
| radio_pluto_19f2-2500000 | radio_pluto_19f2 | 2,500,000 Hz | 4 | 2 | yes |
| radio_pluto_19f2-15000000 | radio_pluto_19f2 | 15,000,000 Hz | 1 | 1 | no |
| radio_pluto_5d4d-2500000 | radio_pluto_5d4d | 2,500,000 Hz | 17 | 0 | yes |

## Portable and refinement model families

The sealed portable execution contains 116 outputs. The evaluator records 116 portable rows, 6 stage-one rows, and 6 fine rows. The two tables show every refined model family; the fine families are the publishable DS2-22 comparison set.

### Stage-one families

| Model family | Post-seal error (km) | RF objective |
| --- | ---: | ---: |
| `baseline` | 3.061 | 0.104296 |
| `shared-time` | 3.061 | 0.104296 |
| `regularized-per-scan-time` | 3.061 | 0.104296 |
| `independent-track-time` | 3.787 | 0.046915 |
| `soft-identity` | 4.052 | 6.151226 |
| `equal-weight-joint-rate` | 3.046 | 0.051132 |

### Fine families

| Model family | Post-seal error (km) | RF objective |
| --- | ---: | ---: |
| `baseline` | 3.159 | 0.104289 |
| `shared-time` | 3.159 | 0.104289 |
| `regularized-per-scan-time` | 3.159 | 0.104289 |
| `independent-track-time` | 3.883 | 0.046912 |
| `soft-identity` | 3.985 | 6.151207 |
| `equal-weight-joint-rate` | 3.235 | 0.051363 |

## DS2-22 versus published DS2-20 fine comparison

| Fine method | DS2-22 error (km) | DS2-20 error (km) | Change (km) |
| --- | ---: | ---: | ---: |
| `baseline` | 3.159 | 1.939 | +1.220 |
| `shared-time` | 3.159 | 1.939 | +1.220 |
| `regularized-per-scan-time` | 3.159 | 1.939 | +1.220 |
| `independent-track-time` | 3.883 | 3.958 | -0.076 |
| `soft-identity` | 3.985 | 2.068 | +1.917 |
| `equal-weight-joint-rate` | 3.235 | 1.924 | +1.312 |

## Geometry and cone evidence

Geometry uses only the original three explicit bindings. Baseline and staged full-FOV estimates are reported separately so that a staged result is never mistaken for a new independent capture.

| Model family | Post-seal error (km) | RF objective |
| --- | ---: | ---: |
| `scan-fw-f3ce5fe73aa40506:baseline` | 115.020 | 0.032320 |
| `scan-fw-f3ce5fe73aa40506:staged_full_fov` | 115.020 | — |
| `scan-fw-9f3d5067d149118e:baseline` | 151.058 | 0.159912 |
| `scan-fw-9f3d5067d149118e:staged_full_fov` | 151.058 | — |
| `scan-fw-cfcf667726e80735:baseline` | 1.589 | 0.037305 |
| `scan-fw-cfcf667726e80735:staged_full_fov` | 1.589 | — |
| `joint-three-geometry-captures:baseline` | 2.763 | 0.066581 |
| `joint-three-geometry-captures:staged_full_fov` | 2.763 | — |

The staged sweep fitted the cone orientation at each tested position for full fields of view from 10° through 90°. The local fitted branch repeated 10° through 50°. Both provisional LT3D-001A RX-to-slot mappings were evaluated and were symmetric; each row below is their stored representative.

| Full FOV | Tracks retained | Occupied support | Held RMS |
| ---: | ---: | ---: | ---: |
| 10° | 4–4 | 5.9–5.9% | 296.8–296.8 Hz |
| 20° | 8–8 | 16.4–16.4% | 192.6–192.6 Hz |
| 25° | 12–12 | 23.4–23.4% | 245.3–245.3 Hz |
| 30° | 20–20 | 38.9–38.9% | 507.9–507.9 Hz |
| 40° | 31–31 | 72.4–72.4% | 480.0–480.0 Hz |
| 50° | 37–37 | 93.3–93.3% | 252.8–252.8 Hz |
| 60° | 40–40 | 100.0–100.0% | 252.8–252.8 Hz |
| 70° | 40–40 | 100.0–100.0% | 252.8–252.8 Hz |
| 80° | 40–40 | 100.0–100.0% | 251.9–251.9 Hz |
| 90° | 40–40 | 100.0–100.0% | 250.3–250.3 Hz |

## Follow-up dispositions

| Follow-up | Disposition |
| --- | --- |
| `consistent-cap800` | completed exact capped-loss search; its winning point is evaluated |
| `rate-aware-screen` | completed bounded rate-aware local screen; its winner is evaluated below |
| `session-scale-residual` | completed diagnostic residual accounting; it does not emit a position |
| `shared-norad` | completed shared-NORAD overlap accounting; it does not emit a position |

### Post-seal positions

| Model family | Post-seal error (km) | RF objective |
| --- | ---: | ---: |
| `consistent-cap800` | 3.039 | 0.051508 |
| `rate-aware-screen:nominal-control` | 3.039 | 0.100062 |
| `rate-aware-screen:rate-aware` | 3.039 | 0.100062 |

## Validation and reproduction

The evaluator rejected unsealed artifacts, incomplete portable/refinement indexes, and artifacts declaring reference or truth use. It bound the completed portable execution, both six-model refinement indexes, geometry inference, the follow-up plan, and every completed follow-up output listed above.

Rebuild the machine-readable evaluation after obtaining the established coordinate through the approved evaluation procedure:

```bash
python postseal_evaluation.py --reference-latitude <lat> --reference-longitude <lon>
python render_evaluation.py
python write_report.py
```

`evaluation.json.sha256` and `comparison.csv.sha256` seal the two machine-readable outputs. `postseal-comparison.png` is rendered solely from the sealed comparison rows.

## Limitations

This is a development evaluation, not an independent holdout result. The post-seal error is useful for comparison but depends on the supplied reference coordinate. The 22-session admission does not create new geometry evidence beyond the original three bindings. Follow-up searches are bounded diagnostics, and candidate identity or orbital interpretation requires separate evidence.
