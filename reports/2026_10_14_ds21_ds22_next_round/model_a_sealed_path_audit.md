# Current sealed Model A path audit and next matched control

This read-only audit uses the current coverage composition (original coverage-v1
for009; cached-v2 unchanged scientific composition for003/023/025), fitted-c only.
Every twelve-unit matrix and training selector is validated before the configured
development reference is joined. No objective, orbit predictor or optimizer is
called. These errors never select a fit or alter a start.

| Case | Selected start | Low error km | Final error km | Low to final movement km |
| --- | ---: | ---: | ---: | ---: |
| 023 | 0 | 8.328325 | 7.758953 | 5.257184 |
| 025 | 0 | 8.229311 | 6.049037 | 2.414331 |
| 003 | 0 | 6.331384 | 2.992063 | 4.026353 |
| 009 | 1 | 2.596828 | 3.155489 | See bound machine audit |

All six A paths are stationary in every audited case. The selected023/025 paths
have no active local25km disk, regional250km disk or physical satellite-timing
box. All selected final paths are interior.003 low has an active timing box;
003 start4 final reaches the25km disk, but that path is not selected. Thus an
active search boundary does not explain the selected023/025 errors.

The original training selector favors023 start0 (objective30973.522,
likelihood30646.334, frequency RMS127.134Hz) over start1 (objective31240.017,
likelihood30949.479, RMS108.818Hz). After seal, their respective location errors
are7.759 and1.170km.025 start4 reaches2.922km, but its objective32017.823 and
likelihood31789.039 are worse than selected start0's30629.717 and30296.455.
Removing the objective's prior contribution would therefore not reverse these
two comparisons. Frequency RMS and location accuracy must be reported separately.

The selected023/025 high stage keeps geography fixed while changing physical
satellite timings by RMS2.433/2.502seconds. This supports a falsifiable timing
intervention; it does not establish that timing movement causes the location
errors. Earlier matched009/013 timing-lock results improved009 and slightly
worsened013, so no full-cohort promotion is justified.

The next control is prespecified on the sealed current023/025 cached parents.
Both conditions inherit each start's own low receipt. Baseline starts1–5 reuse
their validated high/final receipts as metadata. Baseline start0 independently
repeats high/final as an implementation control, comparing seeds/options and
vector, nuisance, objective, likelihood, frequency RMS and offsets with an
absolute tolerance1e-8. The intervention freezes high satellite timing to its
own low fit, fitting the same two receiver offsets. The original final fit and
training selector remain unchanged. Maximum14 new optimizer calls per case,
10 reused baseline high/final calls and6 inherited low fits; each new call20s,
600iterations, fitted-c, same25km disk. Both conditions and the implementation
control must seal before any reference evaluation.

An independent007 input audit also found exact equality of the scientific input
dictionaries, all9 model metadata dictionaries, and all54 vector/nuisance seed
pairs between before007 and coverage007. Coverage007 executed54 new calls and
reused none. Its identical final errors therefore reflect unchanged scientific
inputs, not an expansion improvement or numerical receipt reuse.

Component validation:16 tests passed1.64s, including actual public numerical core
and optimizers with synthetic scientific ports, untouched NumPy serialization,
all12 treatment units with14-new/10-reused accounting, rehashed wrong-low and
numerical-control tampering, added orphan call, failed-attempt retention, and the
preseal reference gate. Ruff passed. Historical failed009 JSON-loader audit is
preserved; a separately named binary-port audit succeeded without scientific calls.
