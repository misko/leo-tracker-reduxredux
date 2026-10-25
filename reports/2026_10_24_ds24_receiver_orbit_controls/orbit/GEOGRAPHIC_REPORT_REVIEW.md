# Independent geographic-report review

Passed. All 24 cases, both c arms and all 144 sealed trial endpoints are accounted for. All 336 published position rows and 14 summary rows match independent recomputation from raw endpoint coordinates. Maximum error discrepancy is 1.13e-12 km and maximum aggregate-statistic discrepancy is 5.82e-13 km. The independent implementation uses spherical vector-angle distance and elementary order statistics rather than the report’s haversine/NumPy functions.

Raw rejected trials remain in the trial statistics. The complete policy uses the trial only when the saved paired RF gates pass; every fallback uses its exact original baseline endpoint in both arms. Trial and policy rows remain separate. No raw trial is silently omitted and no geographic outcome selects an endpoint.

| Model | Adopted pairs | Exact baseline fallbacks |
|---|---:|---:|
| receiver_specific_noise | 18 | 6 |
| receiver_fast_rx1_rf50 | 18 | 6 |
| receiver_fast_rx1_hz50 | 19 | 5 |

No model fits, qualifications, priors or selection rules were changed. GPS was used only in this independent evaluation after the batch seal.
