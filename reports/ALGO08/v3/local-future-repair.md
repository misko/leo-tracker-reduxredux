# Extend forward-owned tracks with measured future support

The fixed-owner repair recovered all nine reachable observations on weak DS30-0016 and retained all 107 original assignments in each calibration arm. It passed the 250 m development tolerance relative to installed ALGO08v3 on physical DS30-0016 and both public simulations. On the northern simulation it retained all 304 forward assignments, whereas solving from the full two-sided packet lost 77 assignments and changed the role of 18 survivors. All three repairs completed the full grid and eight figures with exact endpoint objective replay. [Frozen protocol](local-future-repair-protocol.md) · [Saved publication receipt](measurements/local-future-repair.json.gz)

| Containing offer | Forward → repaired owners per arm | Horizontal error km, v3 fixed / fitted | Forward-only error km | Full two-sided error km | Local repair error km | Local repair RF RMS Hz |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0016 physical | 107 → 116 | 1.644 / 1.661 | 2.473 / 2.542 | 1.320 / 1.697 | 1.479 / 1.849 | 121.19 / 119.95 |
| Northern simulation | 304 → 352 | 0.106 / 0.141 | 0.128 / 0.113 | 0.434 / 0.160 | 0.102 / 0.143 | 6.814 / 6.731 |
| Southern simulation | 266 → 308 | 0.817 / 1.101 | 0.577 / 0.787 | 0.454 / 0.515 | 0.441 / 0.491 | 7.833 / 7.735 |

The weak physical repair improved fixed-zero position by 164 m versus v3 and worsened the fitted arm by 188 m. RF RMS increased by 11.82 / 10.47 Hz relative to v3. The three added predictive observations retained their predictive role. The six added conditional observations joined original conditional groups. The numerical warm refit shifted the endpoints even with the same observation count, satellite and role as the full two-sided fit. The retained original graph and fit context differ between these two designs. [Calibrated scores and admission checks](measurements/local-future-repair.json.gz)

## The archived coverage bound

| Containing offer | Additional owners from full two-sided solve | Genuinely absent from forward packet | Existing same-role satellite on the same radio/RF within 8 s | Local additions / same owner and role as archived two-sided additions |
|---|---:|---:|---:|---:|
| DS30-0016 | 9 | 9 | 9 | 9 / 9 |
| North | 75 | 40 | 33 | 48 / 33 |
| South | 202 | 66 | 42 | 42 / 42 |

The coverage calculation used archived owner labels only after binding the two prior publications. On DS30-0016 all nine observations lay within 3.90 s of the nearest eligible forward owner. In the north, 35 of the 75 newly assigned observations were already present in the forward packet. The equivalent count in the south was 136 of 202. Local attachment has no path to these gains through track reconstruction or role changes. It recovered all 33 reachable northern and 42 reachable southern archived additions. The north also admitted 15 measured future-supported factors outside that archived owner overlap. The earlier publication labels establish disagreement and overlap. The local repair scores them using the forward fit and the unchanged gates. [Archived overlap receipt](measurements/local-future-repair-oracle.json.gz) · [Full two-sided comparison](short-subset-update.md)

## What the repair reads and costs

The preserved forward fit supplies the original graph, phase and RF calibration, track aliases, and bilateral ownership. The bounded reverse continuation supplies 69 physical and 72 observations per simulation for possible attachment. Each nominated measurement must have an existing same-radio/RF forward owner within eight seconds. Both calibrated fits evaluate the same signed alias lift and enforce a 450 Hz point residual ceiling and visibility. The original whole-track profile, noise and alias gates run on the locally extended evidence. A fresh fixed-support paired fit then checks every original owner and role and the original publication support. A second exterior check still uses the forward graph. A failed repair, exterior check, or evidence replay retains the ordinary result. These three containing offers completed directly. [Implementation](local_future_repair.py) · [Routing and fallback](blind_joint_route.py)

| Containing offer | Lane/time hypotheses → paired fits' additions | Forward and reverse selection, CPU s | Local screening and two-arm refit, CPU s | Additional exterior check, CPU s | Whole saved solve, CPU s | Fresh worker CPU / elapsed s |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0016 | 12 → 9 | 0.023 | 0.030 | <0.001 | 2.639 | 5.673 / 5.697 |
| North | 50 → 48 | 0.026 | 0.054 | 0.234 | 3.923 | 7.140 / 7.169 |
| South | 42 → 42 | 0.025 | 0.052 | <0.001 | 3.390 | 6.588 / 6.611 |

The combined selection, local repair and additional exterior CPU totaled **0.053 / 0.313 / 0.077 seconds**. The complete worker clocks include startup, both fit stages, grid evidence and writing and validating all figures. Preparation and numerical fitting read only saved detections and causal metadata. Raw acquisition and durability through the original input reader were not measured. The test used one physical recording and two development simulations, all with the site in the offer. Missing-region discrimination and raw-to-exit timing remain open. [Detailed clocks and branch decisions](measurements/local-future-repair.json.gz)

## Reproduce

Use the same recording-readable account, reviewed geographic and regional libraries and shared low-priority Gauss slot as the [short stereo comparison](short-stereo-evidence.md). Use CPU 2, nice 15, I/O priority 7 and one numerical thread. Run `local_future_repair_oracle.py NEW_ORACLE.json`, then `local_future_repair_trial.py run NEW_DIRECTORY GEOGRAPHIC_LIBRARY REGIONAL_LIBRARY CASE` for `physical`, `north` and `south-inside`, using the release payload ahead of the checkout. After the three sealed publications, run `local_future_repair_trial.py score NEW_DIRECTORY NEW_ORACLE.json NEW_RESULT.json` with the checkout ahead of the payload to access the saved-artifact scorer. The oracle and final publication receipt uncompressed SHA-256 values are `5fcebf373984345e29e4c6229435c0b35819d385e52fd19d8be519a873146b32` and `850aa36a1aad61ca52c3eb0b58a0305de3c7d5c7228e2c0008e9404b48fc5541`. The first oracle invocation treated a raw control's saved-input field as populated. The corrected audit verified its actual signed packet and terminal. The first worker stopped before fitting because the frozen release requires its lazy import hook before scientific imports. The successful launches used fresh output and deferred those imports. Eight focused and adjacent tests passed. [Trial driver](local_future_repair_trial.py) · [Component tests](../../../tests/pipeline_eval/test_local_future_repair.py)
