# Shared-B rejection: free group-offset precision stopping

Both rejected shared/full endpoints replay exactly under the unchanged model. The independent stationarity failure is in an **original free receiver/band offset**, rather than geography, satellite propensity or a copied group state. A one-coordinate Newton estimate predicts only **1.055 objective ULPs on B081 and 6.526 ULPs on B115** at the strongest group coordinate. This supports a numerical precision/stopping explanation for the rejection, without certifying a coupled local minimum or authorizing relaxed stationarity.

| Quantity | DS21-081 | DS22-115 |
|---|---:|---:|
| Original KKT | .001713006364 | .004790541440 |
| Physical projected maximum | .000651339650 | .000530472272 |
| Common-clock projected maximum | .000015451358 | .000017624682 |
| Original-group projected maximum | **.001713006364** | **.004790541440** |
| q projected maximum | .000018069675 | .000023117591 |
| Strongest group analytic chart derivative | −.001713006364 | −.004790541440 |
| Objective central FD, step 1e−5 | −.001710759534 | −.004790126695 |
| Gradient FD curvature | 382443.360174 | 483353.697933 |
| One-coordinate predicted improvement / objective ULP | 1.054534 | 6.525503 |
| Source objective ULP | 3.637979e−12 | 3.637979e−12 |
| Objective evaluations / localization fits | 49 / 0 | 49 / 0 |
| Whole slice including preparation, seconds | 1.669566 | 17.352541 |

Both original solvers report success, but the unchanged strict threshold .001 rejects both endpoints. They returned within their prior numerical budget. The original constructor timing margin is zero at both endpoints; the anchored chart preserves the raw state bit for bit.

The audit probes the two strongest centrally feasible coordinates in each of four blocks at steps 1e−5, 1e−6 and 1e−7. The source has no pairs inside the smooth horizon transition. No probe changes hard visibility or smooth-transition membership. One B081 physical coordinate crosses one interpolation cell at the largest step; its central FD error is 6.079e−7 there, and the two smaller stencils remain in the source cells. Group-offset probes change no support or interpolation cells. Their curvature is stable across all three steps. Smallest-step objective differences show expected ULP quantization; no threshold was weakened to classify them as a passed gradient qualification.

Five active q coordinates in each case are recorded and excluded from centrally infeasible probes, without clipping. Their inward/outward box gradients are included in the independent original projected KKT. Physical NNLS and nuisance-box residual blocks reproduce the original full stationarity. No optimization, Hessian inversion, reference read, truth weighting, original held/locked access or new collection occurred. Coordinate curvature does not establish full-Hessian positive definiteness or prove absence of other model/association errors.

Source `8067dfb78`, [prespecified protocol](MODEL_B_Q_STOPPING_PROTOCOL.md), three component tests pass / Ruff pass. New bulk namespace `model-b-q-stopping-audit-v1`, rooted at `/srv/bulk/leo-research-ds21-ds22/2026_10_14/`, froze original source/input and exact endpoint authority before preparation. Each case had a maximum 61 objective evaluations, 120-second monotonic completion and external 135-second TERM / 140-second KILL; actual 49 each, two single-thread workers. Existing `native_active_endpoint_repair.geometry` supplies the raw original chart and constraints directly to the genuine B SmoothVisibilityModel, with no model reconstruction. All original group offsets, clock, timing, fitted c, priors and own 25 km disks remain unchanged.

Protocol: `sha256:998ac6f07cee26026c02f2a701fea1e61984e4dd171792fa1ce2d9fc37e83743`.

B081 terminal: `sha256:d56bd2c37d076c7406a4a503db1d4763ac51c4fb2367716e06aeeefbbc121ec5`.

B115 terminal: `sha256:0002af8dbe55d10cb2242a911f1b1f17eb71b19cb59490bd9bc8772e294f0681`.

The [12-fit result](MODEL_B_BAND_Q_RESULTS.md) remains unchanged. The next authorized control is matched same-raw-state SLSQP versus safeguarded positive-tangent Newton, retaining original shared-model eligible endpoints and strict independent acceptance. It will be separate extra numerical work, not a retry concealed within the original 20-second budget.
