# A competitive sampled face fails to distinguish valid boundary fixes

The fixed rule abstained on all four saved omissions, including the **South 100 m false fix with both optimizer endpoints in the interior**. It also abstained on both valid 100 m boundary fixes. It retained both wider containing controls. Both calibration arms made the same eight decisions. The exact face score is inexpensive once the full grid exists, but no shared threshold on it separates the tested containing and omitted offers. [Frozen rule](grid-face-abstention-protocol.md) · [Per-face scores and decisions](measurements/grid-face-abstention.json)

## Direct evidence from the sealed loss maps

For each calibration arm, the test subtracts the minimum score anywhere on the original grid from the minimum score at an exact sampled face point. A gap at most **5.9915** witnesses contact with the nominal 95% two-dimensional relative-loss level. The paired check requires both arms to avoid contact before retaining a fix. The sensitivity requiring both arms to make contact before abstaining gave the same outcomes. The underlying variational objective fixes satellite ownership and phase linearization. This is a support-level check on the sampled square, with no calibrated geographic coverage or inference about the exterior. [Grid contract](../../../src/leo/contracts/position_grid.py) · [Implementation](../../../tools/pipeline_eval/variants/experimental/grid_face_abstention.py)

All eight cases had complete grid and path sidecars, exact saved endpoint evaluations, and finite scores on both arms. The final path endpoints, grid endpoints and signed terminal coordinates agreed. The near South pair used the same named-v3 detector packet, orbit archive, owners and named-survivor finish. The near North pair used the same older Q15 input, archive and build. The exact-curved named-v3 North omission summary supplies digests for its grid and path. The audit uses the older complete Q15 North pair for its numerical rows. The wider and 1.5 km pairs use the original regional-v2 publications. Within each pair the native input digest and session match. Across pairs the solver and detector products can differ. All offers and labels were previously public. [South named transfer](named-south-transfer.md) · [North Q15 trial](../single-core-2x/q15-repair-publication.md) · [Original regional release](../regional-release/README.md)

| Saved offer | Truth clearance | Face-loss gap, fixed zero / fitted `c` | Frozen paired outcome |
|---|---:|---:|---|
| North, containing near face | +0.100 km | 0.082 / 0.148 | False abstention |
| North, omitted near face | −0.100 km | 0.045 / 0.026 | Abstain |
| South, containing near face | +0.100 km | 0.864 / 1.144 | False abstention |
| South, omitted near face | −0.100 km | 0.515 / 0.799 | Abstain |
| North, wider containing | +5.797 km | 28.459 / 31.690 | Retain |
| North, omitted | −1.500 km | 0.000 / 0.000 | Abstain |
| South, wider containing | +5.891 km | 51.207 / 53.048 | Retain |
| South, omitted | −1.500 km | 0.000 / 0.000 | Abstain |

On South’s omission, the optimizer endpoints lay **242 / 183 m inside** the east face. On its valid counterpart they were **443 / 383 m inside**. The best archived face sample was at east 12.5 km, north 0 km on both offers. Each east face had nine samples, and that sample was **0.740 / 1.063 km** from the optimizer endpoints in the tangential direction. Both arms flag the South omission as ambiguous despite interior endpoints. The same ambiguity occurs on valid offers.

A threshold selected in hindsight for the South pair would have to lie in **[0.515, 0.864)** with `c = 0` or **[0.799, 1.144)** with fitted `c`. For the complete set, catching South while retaining valid North requires a threshold at least **0.515** and strictly below **0.082** with `c = 0`. The fitted arm requires at least **0.799** and strictly below **0.148**. The paired any-arm and both-arms rules have the same contradictions, respectively. These intervals diagnose crossed rankings. The tested threshold remains **5.9915**.

South's signed horizontal errors were **817 / 1,101 m** on the containing offer and **817 / 1,102 m** on the omission. The corresponding RF RMS values were **6.50230 / 6.39194 Hz** and **6.50234 / 6.39200 Hz**. Fitted calibration reduced RF residual in both offers and increased horizontal error. The receipt keeps the original RF and position outcomes alongside both calibration decisions on all eight offers. [Scored receipt](measurements/grid-face-abstention.json)

## Earlier tests and cost

The mirrored uncertainty experiment applied a local curvature ellipse from a separately replayed containing anchor. The satellite-jackknife experiment estimated an unrestricted local mode and tested face uncertainty from likelihood curvature and whole-satellite deletion. Both found that requiring affirmative containment would lose valid boundary fixes. The grid control-variate experiment used the same sealed South maps to check interpolation errors in rendered contours. Its decision concerned which map values could be estimated. The earlier fixed-owner exterior profile evaluated new locations beyond the offer. I found no earlier experiment applying this exact sampled-face gap to a geographic decision on complete published grids. The new readout reproduces the known ambiguity without extra evaluations. [Mirrored ellipse](../single-core-2x/mirrored-uncertainty.md) · [Satellite jackknife](geographic-jackknife.md) · [Grid contour approximation](grid-control-variate.md) · [Exterior profile](../single-core-2x/exterior-profile.md)

The face readout used **0.10–0.13 CPU ms per grid** after loading and verifying the metadata. It charged no additional objective evaluations. Its applicability depends on the already computed paired position map. It does not establish a pre-solve withholding or runtime gain. The work read existing tmpfs sidecars and public references and performed no new fits or acquisitions. Nine component tests passed. [Driver](grid_face_abstention_trial.py) · [Component tests](../../../tests/pipeline_eval/test_grid_face_abstention.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
out=$(mktemp -d /dev/shm/leo-grid-face-abstention.XXXXXXXX)
script=reports/ALGO08/v3/grid_face_abstention_trial.py
export PYTHONPATH="$PWD/src:$PWD"
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
locked() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c 2 -n 7 taskset -c 2 "$@"
}
locked "$release/venv/bin/python" -BPs "$script" run "$out/predictions.json"
locked "$release/venv/bin/python" -BPs "$script" score "$out/predictions.json" "$out/scored.json"
```
