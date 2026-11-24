# DS30-0008 late family reassignment

Reassigning seven complete hybrid arcs from NORAD 63478 to 67511 moved the fixed-`c` and fitted-`c` endpoints 358 m and 354 m, respectively, from the matched identity refit. Both reassignments passed the original signed gates. The signed objective decreased by 48.26 and 48.68 while position error increased by 337 m and 341 m. A lower in-sample objective would select the less accurate assignment on this recording. [Sealed evidence](measurements/dense-family-refit-0008-sealed.json.gz) · [Position scores](measurements/dense-family-refit-0008-scored.json)

## One conditional comparison

The original [20/12 ms control](exact-solver-0008.md) and [first-192-visit hybrid](dense-8ms-prefix.md) share 4,336 selected observations. Their only shared satellite changes are 222 observations, all from 67511 to 63478 and all after the altered prefix, at visits 3508–5571. These make up seven complete RX1 arcs across 10.7096875, 11.4596875, 11.7096875, and 11.9596875 GHz. Three conditional arcs contain 143 points and four predictive arcs contain 79. The active mask includes every point on the seven arcs. The exact IDs and visit indices are in the sealed evidence.

One saved-only replay captured the hybrid’s signed fit after history qualification. Its terminal, selected rows, eight figures, numerical path and 179-point grid matched the prior publication. The grid’s recorded elapsed time varied. Re-evaluating the captured endpoints restored both signed objectives and both conditional RF RMS values to within `1e-8`. The Python worker denied raw recording reads and reused the validated 47-snapshot pre-cutoff archive.

The treatment merged all seven affected arcs into the hybrid’s existing 67511 assignment, which already retained 416 observations. All other track assignments, observations, aliases, masks, powers, radio noise, and historical prior policy came from the same hybrid context. The moved arcs share the existing 67511 phase and orbital terms. Both assignments passed the original fixed-point track checks, then used the same signed likelihood, matched projection starts and bounds within 5 km per coordinate of each hybrid endpoint, and a common budget of five phase refreshes with 48 optimizer iterations each. The identity refit met the stopping rule after one refresh and the reassignment took two. Both passed the original paired and exterior gates with 3,666 conditional and 703 predictive observations per arm. Position scoring used the DS30 operator site reference after the numerical receipt was sealed.

| Assignment and receiver | `c = 0` position error (m) | Fitted `c` position error (m) | `c = 0` RF RMS (Hz) | Fitted `c` RF RMS (Hz) | `c = 0` signed objective | Fitted `c` signed objective |
|---|---:|---:|---:|---:|---:|---:|
| Published 20/12 ms control | 919 | 857 | 140.961 | 140.950 | 48,420.474 | 48,418.230 |
| Published hybrid | 587 | 530 | 141.278 | 141.294 | 47,330.920 | 47,329.602 |
| Matched hybrid refit with 63478 | 575 | 519 | 141.277 | 141.293 | 47,330.919 | 47,329.602 |
| Matched hybrid refit with 67511 | 912 | 860 | 141.274 | 141.260 | 47,282.659 | 47,280.926 |

Within the held hybrid inputs, the family intervention returns position error close to the published control in both calibration arms. The fitted-`c` objective is lower by 1.32 for the identity and 1.73 for the swap. Fitted `c` decreases position error by 56 m and 53 m respectively, while conditional RF RMS changes by +0.016 Hz and −0.014 Hz. The cross-receiver objective comparison also includes changes in signed RF support. This conditional study establishes the endpoint sensitivity to the late family choice on one packet. It leaves the forward assignment policy and the separate cause of the hybrid’s repair invocation open.

## Single-core cost

The archived saved worker took 26.947 s wall for control and 27.699 s for the hybrid, a 0.753 s increase. The hybrid needed one paired gate repair which removed four tracks and cost 0.738 CPU s in preparation and refitting. Cold search spent 0.839 CPU s more with the hybrid and completed the same number of cold finalists. The signed endpoint update and standard evidence cost 0.080 and 0.122 CPU s less, respectively. Removing the repair cost alone as a wall-time thought experiment leaves the hybrid near the control’s saved wall time. Its repair produced the published full-gate candidate, so that subtraction is a ceiling for savings from avoiding this retry.

The matched two-assignment refit added 3.575 s wall after capture. This was a conditional research evaluation, separate from published worker timing. The named ALGO08v3 target is half of 113.021 s. The archived hybrid saved worker consumes 27.699 s of that budget, leaving 28.811 s wall for authenticated acquisition. The measured original acquisition contributes 32.403 CPU s and 60.449 s wall. An additive CPU budget on one core is 60.097 s using the archived hybrid worker CPU time, 3.586 s above the entire 2× budget. The historical wall-time sum is 88.148 s. This saved replay used the Gauss benchmark lock, CPU 2, nice 15, best-effort I/O priority 7, and six numerical thread settings fixed to one. [Acquisition budget](exact-solver-0008.md)

The [runner](dense_family_refit.py) reads the named saved publications and archive. Its `worker` stage seals endpoints and proof before `score` loads the reference audit using workspace tooling. Twelve focused component and neighbor tests passed. [Component tests](../../../tests/pipeline_eval/test_dense_family_refit.py)
