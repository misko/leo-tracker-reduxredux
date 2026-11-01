## Findings and recommendation

**The frozen combined candidate improves the DS26 tail, but does not solve typical accuracy or the worst failures. Keep ALGO06 in production for now.** Across 148 DS26 outcomes, fitted-c mean error falls from 1.296 to 1.208 km (6.7%), P90 from 2.424 to 2.176 km, and P95 from 3.551 to 2.939 km. Median error is essentially unchanged (0.983 to 0.982 km), and the number below 500 m rises only from 25 to 26. The matched c=0 mean also improves, from 1.313 to 1.226 km. All 13 DS27 and 14 DS28 outputs are unchanged. Of 175 usable outcomes, 174 searches completed and one retained ALGO06 after the fixed compute cap; 15 upstream unavailable acquisitions remain separately accounted.

The four whole-family identity corrections are supported by RF-only selection:

| DS26 scan | Incumbent → replacement NORAD | Fitted-c error, ALGO06 → combined | Interpretation |
|---|---|---|---|
| 0034 | 53852 → 59188 | 4.498 → 0.374 km | Reproduces the development repair; improves held-receiver prediction, but the endpoint remains gate-margin sensitive. |
| 0044 | 57414 → 63186 | 3.715 → 1.580 km | Additional scan; improves both held-receiver predictions and is stable under the tested gate-margin changes. |
| 0066 | 62025 → 68047 | 2.370 → 1.218 km | Additional scan; requires combined history and reassociation. All five whole-track holdouts improve in both c arms. Target evidence is RX1 only, so cross-receiver validation is unavailable. |
| 0251 | 56548 → 58787 | 6.561 → 1.162 km | Reproduces the development repair; reassociation alone reaches 1.949 km, and causal history improves physical-mode uncertainty and transfer. |

No accepted destination identity was already owned by another baseline family. These are replacements using the same native points, not increased coverage: DS26 stays at 71.256% associated, DS27 at 78.252%, and DS28 at 74.969%.

**Most aggregate improvement comes from already investigated cases.** Excluding four development and eight pilot scans, the remaining 149 DS26/DS27 outcomes improve from 1.139 to 1.116 km mean fitted-c error. The descriptive paired bootstrap interval for the mean change is −59.7 to +0.1 m, spanning zero. The two additional identity corrections are encouraging, but this is not yet strong evidence of broad accuracy gains across new sites or hardware.

**Completing history is not uniformly helpful.** History-only changes six scans and improves DS26 mean by just 3.4 m. DS26-0058 regresses from 0.977 to 1.074 km fitted-c and 1.001 to 1.094 km with c=0, despite passing RF selection. Causal completion broadens phase uncertainty for 59523 and 67521; for 67521 it also tightens radial uncertainty while broadening cross-track uncertainty. This is a mixed prior change, not evidence that phase width alone causes the regression. The detailed export is retained in [history_mechanism.json](DS26-0058/history_mechanism.json). GPS error was not used to override this accepted outcome.

**Predictive gains and stable localization are different requirements.** All reported held-receiver replacement comparisons improve RMS and normalized predictive score with closed training-only phase updates. DS26-0066 also improves every whole-track holdout, but some alternative gate/prior settings fail acceptance. Its approximately 0.422 km fitted-c result with the larger tested margin fails gates and is not an achieved valid correction. DS26-0034 is also margin-sensitive. DS26-0044 is the clearest additional repair under the tested margin changes. None of these tests supplies a calibrated probability of unique identity.

The worst fitted-c failures, DS26-0203 (6.858 km) and DS26-0070 (6.716 km), remain unchanged. A one-family conditional replacement cannot establish whether these need several simultaneous identity changes, different track ownership, or a better shared receiver/orbit model. This experiment also does not isolate hardware sample rate or pointing as a cause.

Recommended next steps are to implement a bounded production-shaped reassociation path with exact ALGO06 fallback; retain paired c controls and native-owner checks; examine the 0058 prior change with a component ablation; and debug the two unresolved worst scans using joint-family alternatives and receiver-versus-satellite residual structure. Evaluate that frozen implementation on new recordings before promotion. Avoid choosing a gate margin, receiver prior, or selective history policy from the evaluation GPS errors. The current four-variant research runtime is not an embedded or single-policy production benchmark. No new ALGO number or deployment follows from this report.
