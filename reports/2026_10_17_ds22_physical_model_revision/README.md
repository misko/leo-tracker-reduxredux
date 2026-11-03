# DS22 full-membership association and physical-model investigation

All 137 original DS22 entries now have Graph tracks and eight matched fixed-site
association arms. The former gap of 68 adaptive inputs has been closed using
existing public-port products, with no RF collection or GLRT re-analysis.
Satellite identities remain frequency-compatible candidates, not verified IDs.
The sub-0.5-km geographic requirement remains unachieved.

## Membership and timing authority

The 68 adaptive exports bind the exact raw-capture manifest digests in the
original sealed DS22 dataset, with identical UTC origins. Their device sample
counters retain gaps and within-visit probe offsets. Their actual sample rate
is 10 MS/s; no rate was inferred from the older fast-scan format. Graph fitting
separates receiver/channel/actual RF lanes. One maximum-margin gate-passing
fractional peak is retained per physical probe; no observations are held out.

DS22-137 was only four completed raw segments (2,048 windows) in the original
seal. The later finished capture has fourteen segments. The four original
segment digests match its prefix exactly; all 32 original index chunks were
hash-verified. Only probes within those exact original device-counter windows
enter the main comparison. The resulting 2,094 processed receiver probes yield
948 gated winners and 861 Graph points. The longer completed capture remains
under `fast_recovered*` as an explicitly excluded extension; its points do not
enter any full-corpus total below. Earlier sealed reports remain unchanged.

## Track construction

The same frozen Graph/trimmed policy is used across capture formats. Detector
rate, RF/channel coverage and available probe density differ, so these totals
are not a controlled detector or cross-format performance comparison.

| Format | Entries | Gated winners | Graph points | Graph % | Graph tracks | Hard merged | GLRT points/Graph track |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fast | 69 | 244033 | 216900 | 88.88% | 7146 | 6149 | 30.35 |
| adaptive | 68 | 100761 | 80977 | 80.37% | 3367 | 3309 | 24.05 |
| all | 137 | 344794 | 297877 | 86.39% | 10513 | 9458 | 28.33 |

![Full-corpus coverage](full-corpus-coverage.png)

## Fixed-site satellite compatibility

The supplied site is 37.849061591561885, -122.48574968092912 (assumed ellipsoidal height 0 m). Latest eligible causal Space-Track elements are chosen before each scan; neither future epochs nor future collection times enter. Candidates use the same broad regional prior in each arm. Every scan retains four receiver/band offsets and four small linear drifts (sigma 2 Hz/s, bounds ±5 Hz/s here). Only measured-curved fragments calibrate; linear tracks can be associated afterward. Groups absent from a capture are not measured calibration.

Each c=0/fitted-c pair holds original points, candidates, priors and budgets matched. A 1,000-Hz component-bias prior is a carrier-offset hypothesis; no free component slope is fitted. Admission still requires RMS ≤450 Hz, residual-structure checks and bounded bias. Percentages use all gated original winning GLRT points, not just Graph points. No independent identity accuracy is available.

| Format | Bias sigma Hz | Grouping | RF arm | Entries | Compatible groups | Points | GLRT % | Points/group |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| adaptive | 0 | fragments | c=0 | 68 | 45 | 828 | 0.82% | 18.40 |
| adaptive | 0 | fragments | fitted c | 68 | 58 | 1114 | 1.11% | 19.21 |
| adaptive | 0 | hard merged | c=0 | 68 | 44 | 827 | 0.82% | 18.80 |
| adaptive | 0 | hard merged | fitted c | 68 | 54 | 1095 | 1.09% | 20.28 |
| adaptive | 1000 | fragments | c=0 | 68 | 598 | 9903 | 9.83% | 16.56 |
| adaptive | 1000 | fragments | fitted c | 68 | 598 | 9907 | 9.83% | 16.57 |
| adaptive | 1000 | hard merged | c=0 | 68 | 575 | 9564 | 9.49% | 16.63 |
| adaptive | 1000 | hard merged | fitted c | 68 | 579 | 9751 | 9.68% | 16.84 |
| all | 0 | fragments | c=0 | 137 | 143 | 2965 | 0.86% | 20.73 |
| all | 0 | fragments | fitted c | 137 | 184 | 4087 | 1.19% | 22.21 |
| all | 0 | hard merged | c=0 | 137 | 110 | 2264 | 0.66% | 20.58 |
| all | 0 | hard merged | fitted c | 137 | 138 | 3322 | 0.96% | 24.07 |
| all | 1000 | fragments | c=0 | 137 | 1850 | 35305 | 10.24% | 19.08 |
| all | 1000 | fragments | fitted c | 137 | 1849 | 35278 | 10.23% | 19.08 |
| all | 1000 | hard merged | c=0 | 137 | 1465 | 27827 | 8.07% | 18.99 |
| all | 1000 | hard merged | fitted c | 137 | 1488 | 29416 | 8.53% | 19.77 |
| fast | 0 | fragments | c=0 | 69 | 98 | 2137 | 0.88% | 21.81 |
| fast | 0 | fragments | fitted c | 69 | 126 | 2973 | 1.22% | 23.60 |
| fast | 0 | hard merged | c=0 | 69 | 66 | 1437 | 0.59% | 21.77 |
| fast | 0 | hard merged | fitted c | 69 | 84 | 2227 | 0.91% | 26.51 |
| fast | 1000 | fragments | c=0 | 69 | 1252 | 25402 | 10.41% | 20.29 |
| fast | 1000 | fragments | fitted c | 69 | 1251 | 25371 | 10.40% | 20.28 |
| fast | 1000 | hard merged | c=0 | 69 | 890 | 18263 | 7.48% | 20.52 |
| fast | 1000 | hard merged | fitted c | 69 | 909 | 19665 | 8.06% | 21.63 |

## Lossless candidate-guided consolidation

Hard pre-merging can lose compatible points. This alternative begins from admitted original fragments and only joins compatible same-NORAD candidates with shared calibration, one constant component bias and residual checks. Failed joins retain both fragments. Every admitted point and candidate identity is preserved.

| RF arm | Input fragments | Output groups | Points retained | GLRT % | Points/group |
| --- | --- | --- | --- | --- | --- |
| c=0 | 1850 | 1689 | 35305 | 10.24% | 20.90 |
| fitted c | 1849 | 1677 | 35278 | 10.23% | 21.04 |

## Carrier-bias and UTC diagnostics

A new RF-proportional carrier-bias hypothesis contributes `(RF/11.5 GHz)*b` with a zero-mean Gaussian prior of 1,000 Hz at the reference. This prior imposes a hardware/carrier gauge; it is not independent calibration evidence. Unit tests compare its marginal Gaussian quadratic and determinant against a dense covariance calculation. Native alias spacing and the zero-bias nested model are preserved.

Both bias families were scored at the supplied site and previously sealed blind endpoints, with UTC shifts at the midpoint and the two declared bracket ends. Both c arms use identical observations, candidates, priors and budgets. These are diagnosis locations only and cannot seed the next blind search. Across both cases, improved frequency fit still leaves the wrong endpoint preferable. Merely changing native bias to RF-proportional bias, or profiling the allowed UTC bracket, does not solve the geographic error. An additional frozen-calibration saturation diagnostic from 150 to 900 Hz also retains the wrong-site preference.

![Physical-model diagnostic](physical-model-diagnosis.png)

| Case | Carrier-bias model | RF arm | Fixed scoring site | Best sampled UTC shift s | Penalized frequency score |
| --- | --- | --- | --- | --- | --- |
| DS22-001 | native | c=0 | supplied_evaluation_site | -0.124731 | 724335892 |
| DS22-001 | native | fitted c | supplied_evaluation_site | -0.124731 | 722715807 |
| DS22-001 | native | c=0 | previous_blind_endpoint | -0.124731 | 579740544 |
| DS22-001 | native | fitted c | previous_blind_endpoint | -0.124731 | 578813469 |
| DS22-001 | rf_scaled | c=0 | supplied_evaluation_site | -0.124731 | 716668856 |
| DS22-001 | rf_scaled | fitted c | supplied_evaluation_site | -0.124731 | 715483469 |
| DS22-001 | rf_scaled | c=0 | previous_blind_endpoint | -0.124731 | 578497169 |
| DS22-001 | rf_scaled | fitted c | previous_blind_endpoint | -0.124731 | 576484616 |
| DSX01-S01 | native | c=0 | supplied_evaluation_site | -0.125014 | 716221242 |
| DSX01-S01 | native | fitted c | supplied_evaluation_site | -0.125014 | 716316110 |
| DSX01-S01 | native | c=0 | previous_blind_endpoint | -0.125014 | 703159440 |
| DSX01-S01 | native | fitted c | previous_blind_endpoint | -0.125014 | 701641914 |
| DSX01-S01 | rf_scaled | c=0 | supplied_evaluation_site | -0.125014 | 681732241 |
| DSX01-S01 | rf_scaled | fitted c | supplied_evaluation_site | -0.125014 | 682055124 |
| DSX01-S01 | rf_scaled | c=0 | previous_blind_endpoint | -0.125014 | 662689360 |
| DSX01-S01 | rf_scaled | fitted c | previous_blind_endpoint | -0.125014 | 664787642 |

A recent experimental study reports channel-dependent Doppler biases and CFO correction behavior, including synchronized channel clusters: [Saroufim, Hayek and Kassas, Mind the Beam (ION GNSS+ 2026)](https://www.ion.org/publications/abstract.cfm?articleID=20898). This motivates checking transmitter behavior; it does not establish which mechanism affects our recordings.

## Blind adaptive position pilots

The pilots were preselected without geographic error: DS22-002 is the first adaptive entry; DS22-058 has the most points in individually measured-curved Graph fragments (ranking retained). The unchanged uniform 81-point regional grid, three basins and eight full-budget finalists use all original Graph points. The evaluation GPS is supplied only after each fit is frozen. These are bounded pilot searches, not a complete 137-recording position evaluation or proven global optima.

| Recording | RF arm | Position error km | Original Graph points | Geographic evaluations |
| --- | --- | --- | --- | --- |
| DS22-002 | c=0 | 5.861 | 1310 | 196 |
| DS22-002 | fitted c | 5.861 | 1310 | 196 |
| DS22-058 | c=0 | 4.750 | 1612 | 214 |
| DS22-058 | fitted c | 4.824 | 1612 | 218 |

## Causal orbital sensitivity

The latest selected TLE was compared with the newest available **distinct older epoch** collected before the same causal cutoff, within the same 48-hour archive window. No future element, observation or candidate set was introduced. Both predictions were propagated at 13 times over 300 seconds. Doppler disagreement is evaluated at the original broad regional center (37.5, -122), with the best affine difference removed to expose shape changes.

| Case | Subset | NORADs | Position median km | Position p90 km | Shape median Hz | Shape p90 Hz |
| --- | --- | --- | --- | --- | --- | --- |
| DS22-001 | all compared candidates | 1415 | 25.069 | 81.966 | 51.1 | 1193.5 |
| DS22-001 | admitted candidate NORADs | 8 | 35.657 | 70.667 | 3324.8 | 9282.2 |
| DSX01-S01 | all compared candidates | 1656 | 6.181 | 28.430 | 15.0 | 323.8 |
| DSX01-S01 | admitted candidate NORADs | 12 | 7.050 | 12.955 | 666.9 | 957.5 |

![Causal orbit disagreement](causal-orbit-disagreement.png)

These differences are substantial, including for NORADs admitted by the fixed-site frequency model. They demonstrate sensitivity to the orbital input, not the true error of the latest TLE or proof of an association. Objects without a previous distinct causal epoch are absent only from this diagnostic; they remain in association candidate sets. The earlier candidate IDs are not independent identity labels. The current experiments still use the latest causal TLE without orbital correction.

A new pure geometry port separates satellite orbital-phase perturbations from receiver UTC shifts: states at `t+delta` are rotated back to Earth orientation at observation time `t`. The zero-phase model exactly nests existing geometry. This is preparation for a physically constrained, per-NORAD shared correction experiment; no corrected position solution is claimed here. Future corrections must be shared across all assigned tracks of a satellite, retain priors and complexity costs, and be evaluated with matched c arms and blind geographic initialization.

No pilot meets 0.5 km. Improved frequency fit, merged-group counts and a completed corpus pass are not evidence of geographic success. `cohort.json` maps every original entry to its frozen observations, association artifacts and consolidation; machine-readable comparisons, all controlled failures/extensions and the active checkpoint accompany this report.
