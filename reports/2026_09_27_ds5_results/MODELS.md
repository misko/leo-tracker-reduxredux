# Model catalogue: DS5 comparison and DS6 transfer

This catalogue covers all **24 registered DS5 methods**, plus the subsequent
drift/refinement/information prototypes. Historical iteration labels are not
counted as extra executed DS5 methods. See the historical coverage links below
for earlier DS1–DS4 work. A completed run is not necessarily a converged or
well-calibrated estimator.

## Common measurement model

The raw measurement is received carrier-frequency evidence along an observed
track. Orbital propagation predicts Doppler at a candidate receiver location,
satellite identity and observation UTC. A fitted constant CFO for each track
absorbs its unknown frequency zero. Position, identity and optional timing/orbit
parameters are selected using signal residuals. Every recording retains its own
UTC timestamps: fitting a shared time correction does not make the scans
simultaneous. None of the reported positions is selected by reference error.

Per-scan source products used by point/surface methods were already fitted by
the scanner's blind Sacramento-prior search. Aggregation does not independently
re-estimate their satellite identities or timing. The geographic prior is
Sacramento-centred with a 250 km radius; a finite search budget limits explored
resolution and can leave competing basins unresolved.

## Six position aggregation methods

These fit one combined receiver location from previously selected per-scan
positions. No additional Doppler or timing nuisance parameters are fitted here.
All six reduce to the supplied position when the input contains one scan.

| Method | What is computed/fitted | Motivation and principal limitation | DS5 full error km |
|---|---|---|---:|
| Equal spherical mean | Equal-weight mean on the sphere | Simple control; an inaccurate scan can move the result | 2.229 |
| Inverse-RF-RMS² mean | Spherical mean weighted by inverse squared RF residual RMS | Favours good signal fits, but RF RMS is not calibrated position variance | **1.459** |
| Lowest-RF-RMS 75% | Keep the lowest-residual 75% of scans, then average | Rejects poor signal fits; may discard useful geometry | 2.497 |
| Spatially trimmed 75% | Keep positions near a robust centre, then average | Rejects spatial outliers; a shared wrong basin can still dominate | 2.362 |
| Geometric median | Location minimizing summed distances to scan estimates | Robust to isolated outliers; can retain grid-point quantization | 5.791 |
| Iterative Huber centre | Iteratively downweight distant scan positions | Softer rejection than trimming; does not remove common bias | 2.484 |

## Four objective-surface methods

Each scan supplies a geographic signal-loss surface. These methods combine
surfaces and estimate a local sub-grid minimum using a quadratic fit. The
quadratic must pass numerical rank, curvature, fit-quality and support checks.
It is an interpolation of the scored surface, not new RF evidence or a calibrated
position covariance.

| Method | Surface transformation | Motivation and limitation | DS5 full error km |
|---|---|---|---:|
| Raw capped MSE | Combine capped mean squared frequency residuals | Uses shape away from a scan's winner; scan scale can dominate | 3.667 |
| Delta MSE | Subtract each scan's minimum before combining | Invariance control; subtracting constants should preserve the raw winner | 3.667 |
| IQR-scaled delta MSE | Normalize relative loss by each surface's interquartile range | Balances surface scales; weak surfaces can receive excess influence | 3.223 |
| Fractional rank | Replace surface losses by within-scan ranks | Robust to loss units; discards meaningful objective spacing | 4.017 |

## Eight raw-track timing/association methods

All fit a common receiver position for the input unit and per-track constant
CFOs. Candidate identity is reconsidered according to the method's association
contract. Scans are weighted equally in the portable timing adapter; within a
scan, track support uses occupied seconds. These are full-input positioning
experiments, not all held-out prediction experiments.

| Method | Additional fitted parameters | Association and caveats | DS5 full error km |
|---|---|---|---:|
| Baseline | No clock correction; tau fixed at zero | Hard candidate selection at each geographic point | 8.329 |
| Shared global time | One time correction for every scan/track/satellite in the unit | Absorbs a common epoch offset; cannot capture independent scan errors | 8.329 |
| Regularized per-scan timing | One global time plus bounded, penalized corrections for individual scans | Balances common clock and scan deviations; identical selected result here does not imply identical models | 8.329 |
| Independent per-track timing | A separate time correction for each track | Flexible diagnostic; can absorb wrong identities or position errors and needs stronger validation before deployment | **4.231** |
| Causal per-NORAD orbit rate | One bounded phase/time-rate correction per selected NORAD, evolving with TLE age | Staged hard association followed by joint rate fitting; exact orbital replay; not a full soft identity/rate search | 7.286 |
| Global time + per-NORAD rate | Shared time plus per-NORAD age-dependent rate terms | Separates common epoch and orbit-age evolution imperfectly; extra confounding | 7.286 |
| Soft identity mixture | Candidate probabilities/evidence plus candidate-specific CFOs | Marginalizes alternatives with a signal/null model; mixture scores do not prove correct identities | 7.286 |
| Soft identity + global time | Same mixture plus a single shared time correction | Jointly handles ambiguity and epoch offset; still bounded search | 7.286 |

The per-scan timing adapter uses a quadratic correction penalty and a bound on
deviation from global tau. Actual executed configurations, source hashes and
fitted parameters are in the sealed task/inference receipts on RAID. A causal
orbit-rate term is an orbital timing/phase correction, not a free linear CFO
drift for every track. The soft mixture uses a robust signal likelihood and null
component; it is not simply assigning equal weight to all satellites.

## Two exact full-dataset methods

| Method | What is selected | Validation and search limitation | DS5 full error km |
|---|---|---|---:|
| Cell-batched reselection score | Position with point-local candidate/nuisance reselection, streamed over exact orbital predictions | 42 sessions; best point lies on 2 km grid edge; objective is selection loss | 4.910 |
| Cell-batched exact crossfit | Train-selected identity/time, then held-out geographic scoring with equal-session weighting | 42 sessions and 25 cells replayed; selected global tau -1 s; best geographic point lies on grid edge | 4.104 |

The full42 results above do not imply that all 52 DS5 units were run for these
two families. They were not. Different objective definitions explain why their
reported residual RMS values should not be compared as the same statistic.

## Four registered geometry methods: unavailable on DS5

| Method | Parameters/constraint | DS5 status |
|---|---|---|
| Fixed hard cone | Fixed direction and opening angle reject invisible candidate directions | Not applicable: no capture-time geometry binding |
| Learned cone quantiles | Infer a view envelope from candidate directions/support | Not applicable: no capture-time geometry binding |
| Staged full-FOV sweep | Compare prescribed opening angles, fitting permitted orientation | Not applicable: no capture-time geometry binding |
| Local fitted-cone positioning | Joint/local position and permitted viewing-direction fit | Not applicable: no capture-time geometry binding |

These are 208 explicit N/A method/unit rows, not successful geometry runs and not
missing zeros. Earlier cone experiments do not establish DS5 coverage. DS6 has
pose attachments, but the physical/software RX mapping and directed RF baseline
remain provisional; no geometry-driven DS6 result is claimed by this transfer.

## Subsequent sub-km prototypes

| Experiment | Parameters or computation | Actual completed evidence | Remaining work |
|---|---|---|---|
| Multi-basin refinement | Refine signal-selected basins at 1 km, 500 m, 250 m and 125 m; reuse exactly matching cached cells | Adapter and synthetic boundary/cache tests | No completed real fine-grid estimate |
| Common receiver drift | Track intercepts plus common frequency slope; optional RX deviation; compare no correction/time/drift/both | One scan, 58 tracks, 2,169 observations; exact ±5 s replay in 0.5 s steps; best time 0 s | Multi-scan regularized model and position benefit unproven |
| Information weighting | Project east/north Doppler derivatives off nuisance columns; cap correlated support | Local frozen-association information eigenvalues 179.85/523.89, condition 2.91 | Not calibrated uncertainty; no demonstrated new positioning error |
| Influence/stability | Leave out groups/scans/identities and inspect movement or reranking | Prototype/tests and one-scan diagnostics | Full leave-scan/satellite-out position refits unfinished |
| Dwell metadata audit | Distinguish configuration, valid duration, interval union/intersection and completeness | All 42 scans inspected; configured 120/240/360 ms but realized valid visits 120 ms | No causal dwell-duration accuracy conclusion |

Drift improved training residual RMS from 222.569 to 222.489 Hz but worsened
held-out RMS from 235.891 to 236.096 Hz. Timing alone selected zero correction.
The fitted drift was 2,232.709 Hz/hour. This is evidence against claiming a gain
from that particular one-scan nuisance extension, not a proof that all receiver
drift modelling is useless.

## DS6 results and execution coverage

DS6 consists of 43 separately frozen roof recordings. Its operator-provided
reference is 37.849056280893684, -122.48575489722863, introduced only after
inference. It is a different reference from DS5 and is not surveyed truth.

| Method selected on DS5 | DS6 single median km | DS6 group8 median km | DS6 full43 km | Status |
|---|---:|---:|---:|---|
| Inverse-RF-RMS² mean | 6.528 | 3.018 | 1.978 | Complete: 49 input units |
| Lowest-RF-RMS 75% | 6.528 | 3.437 | 2.680 | Complete: 49 input units |
| Baseline raw-track control | Pending | Pending | Pending | Planned/running separately |
| Shared-time raw-track control | Pending | Pending | Pending | Planned/running separately |
| Independent per-track time | Pending | Pending | Pending | Planned/running separately |

No DS6 accuracy claim is made for a pending method. The three raw-track arms have
a separate sealed 147-task plan (49 units each). The two completed fast methods
use 400-point, 12.5 km source searches; all exhausted their budgets. Averaging can
improve empirical error without establishing converged per-scan positions.

## Historical coverage

Earlier DS1–DS4 experiments include cone-angle/orientation sweeps, shared timing,
causal orbit correction, sequential priors, information weighting, rate-bound
audits, and numerical surrogate/refinement iterations. Those results use different
datasets and sometimes different references and validation contracts. They are
not pooled into the DS5 table or relabelled as new DS5 runs.

- [Historical DS1/DS3 registry](../2026_09_25_ds1_ds3_all_methods/method-registry.json)
- [DS5 executed-method registry and exclusions](../2026_09_26_ds5_all_methods/method-registry.json)
- [DS5 all completed point/surface/portable metrics](comparison-table.md)
- [DS5 exact results](../2026_09_27_ds5_exact_summary/REPORT.md)
- [DS6 completed fast transfer](../2026_09_27_ds6_fast_transfer/REPORT.md)

In particular, historical I15 information weighting was invalidated by the
corrected rate-bound audit, and I26's quartic rate-marginal surrogate was
superseded. Neither is counted as a validated DS5 positioning method. Sequential
DS3→DS4 location-prior transfer answers a different continuing-station question
and was excluded from the standalone DS5 comparison.
