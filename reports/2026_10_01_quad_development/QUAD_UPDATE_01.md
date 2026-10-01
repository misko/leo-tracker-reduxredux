# Recursive quad pilot: accepted, slower, no meaningful accuracy gain

All three metadata-first recursive quad pilots pass the unchanged numerical audit. They use the two constituent-pair-v3 winners as starts, copy scan-specific nuisance values, recompute assignments and jointly fit the original quad objective. Every charged pair total already includes its singles; quad preparation and fitting add to that total once.

| Pilot | Baseline error | Recursive error | Baseline wall time | Recursive charged time |
|---|---:|---:|---:|---:|
| DS9-B01-Q | 1,365 m | 1,359 m | 170.1 s | 261.1 s |
| DS10-B01-Q | 146 m | 193 m | 195.8 s | 265.5 s |
| DS11-B01-Q | 455 m | 455 m | 149.3 s | 242.3 s |

All remain within the same 360-second allowance. These three results provide no reason to promote the recursive method: it adds charged work, barely changes DS9/DS11 and slightly worsens DS10. They do establish that real scan-state transfer and timed worker preparation execute successfully under the numerical audit. Preserve the remaining thirteen planned quads to assess failures and cases outside this pilot rather than generalizing from three examples.

The next queue runs at most two new quads per invocation, verifies source/input seals and skips only already sealed outcomes. Missing or rejected pair constituents remain explicit failures, including the known rejected DS11-B03-D2. No alternate pair is substituted. The sixteen fixed quads and source recipe are frozen by the queue before additional fits.

The [pair gradient diagnosis](GRADIENT_DIAGNOSIS.md) separately identifies a background-score discontinuity in that rejected constituent. Its figure and fixed-state perturbations are diagnostic evidence, not a relaxed audit or repaired fit. Smooth visibility weighting is a future model hypothesis, and is not combined with this recursive arm.

Pilot evidence is retained under `recursive-quad-v1/DS9-B01-Q`, `DS10-B01-Q` and `DS11-B01-Q`, including numerical audits and launch/source/input receipts. The [preflight](recursive-quad-preflight-v1.json) and [plan](RECURSIVE_QUAD_PLAN.md) describe the state mapping and accounting rules. These are correlated development cases using the operator reference; no held-out or calibrated-uncertainty claim follows.
