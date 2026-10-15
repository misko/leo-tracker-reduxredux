# B071 numerical repair completes CV without validating a localization fix

Both rejected fixed q fold1 profiles now have accepted numerical repairs under the unchanged .001 KKT gate. The complete twofold predictive comparison still favors the conditional baseline at the original all geography. No full FREE continuation, reference comparison, original held/locked access or localization promotion occurs.

| Fixed source / extra method | Strict accepted | KKT | Own-fold J | Actual objectives incl audit | Numerical seconds |
|---|---|---:|---:|---:|---:|
| all / SLSQP repeat | true | .000830068 | 14999.775898667423 | 12 | .065607 |
| all / positive-tangent Newton | true | 2.478e−8 | 14999.775898665383 | 280 | 1.460600 |
| high / SLSQP repeat | false | .002848607 | 16663.553324388155 | 14 | .077965 |
| high / positive-tangent Newton | true | 9.413e−10 | 16663.553324387200 | 276 | 1.426488 |

The original all/high failures remain saved as failures. The all endpoint is repaired by either method; the high endpoint is repaired only by the PD method in this comparison. Therefore extra SLSQP work sometimes suffices, but did not repair both cases here. No tolerance was relaxed. Own-fold training minimum selects PD for both fold1 geographies; original accepted fold0 endpoints remain unchanged.

The complete unregularized affine-tangent Hessians have dimensions138/136, minimum eigenvalues .076550178/.077032335 and maximum eigenvalues741113.741230/535679.608438. Both pass the unchanged relative PD threshold and full Cholesky. Raw antisymmetry maxima are .000292328/.000220466; all eigenvalues, Cholesky diagonals and active constraints are retained in returned receipts. Fixed XY contributes two affine normals, with four/six active lower q bounds. No curved constraint is active. Coupled objective decreases are approximately2.02e−9/9.55e−10; the preceding coordinate-only ULP estimates were not coupled-Hessian predictions.

All four outcomes sealed before eight opposite-fold objective evaluations. Proper conditional CFO NLL excludes priors; the original joint-event score is reported separately:

| Geography / observation arm | Twofold conditional CFO NLL | Twofold event score |
|---|---:|---:|
| all / conditional **best predictive** | 39063.517410 | 42715.578593 |
| all / q | 39142.280973 | 42816.703212 |
| high / conditional | 39252.167945 | 42907.434220 |
| high / q | 39207.433905 | 42879.821357 |

q is **78.763562 worse** than conditional at the all geography and44.734040 better at the high geography. Within q, high loses65.152932 to all. This aggregate masks opposite fold signs: high-minus-all q predictive loss is +304.777399 on fold0 and −239.624467 on repaired fold1. q-minus-conditional losses also vary by fold/band: all fold0 low−167.802458/high+7.493639, all fold1 low+96.491714/high+142.580667; high fold0 low+7.503792/high−60.133586, high fold1 low−88.998390/high+96.894144. There is no consistent predictive improvement across folds and both bands in this case. Shared full-derived discovery, frame, geographies and initialization retain the original conditional-development-CV limitation.

The new eligible inventory is **fold1-all-PD and fold1-high-PD**, complete states on their own original25km disks and own fitted fold. all-repeat is also accepted but loses its own-fold selector; high-repeat remains rejected. Original fold0 q all/high states and four conditional states retain their previous provenance. The selected fold1 q states have not been independently replayed for full-target KKT or continued on full training. Their eligibility here is source-fold fixed-XY eligibility only. The prior full q distant selection remains unchanged; no accuracy claim follows from the repaired CV gate. Further full continuation requires a separate declared inventory/qualification, rather than automatic retries or truth-selected starts.

Source/protocol `34f5c7353` (own driver/test/protocol; unrelated staged C019 files were included by a shared-index race, without edits to their bytes). Thirteen driver/shared-core tests PASS1.85s and Ruff preceded source freeze. Zero-fit qualification passed four objectives in28.503s with exact original/recorded objective, gradient, posterior/residual and fixed-domain KKT replay. New numerical work totaled582 actual objectives across four calls, each below20s/600 including independent audit; whole units31.522–33.325s include preparation/authority checks. The8-objective predictive evaluation took28.485s. No new parameters, clock terms, RF data, candidate selection, bounds or prior tuning were introduced.

Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-b071-fold-repair-v1`; qualification SHA256 `ab9b7c2122256203858838a7af886239fb388f376d64a1942d560ba0ff253e39`; all-four seal `5a5479ef49e0ea737d684c1c22a43e8570894a682b44f272bd1ce8cf5c6ae16d`; postseal predictive evaluation `31b8979e977034531dc8c39cf4d13cfd02b58bc09391402e4b5b2098f8b64936`. Four calls are additional to original18 B fits, eight CV profiles and six prior full continuations, not an equal end-to-end budget claim.
