# DSX01 S01: largest remaining GLRT track and first later TLE

RX1 CH2 T000 is strongly consistent with **STARLINK-32847 (NORAD 62811)**, but remains unassociated under the full residual rules. A later TLE does not resolve it. There is evidence of an additional RX1 fluctuation component shared across different satellite candidates, alongside an unresolved slower shape discrepancy. No production assignment or calibration was changed.

This investigation follows the [shared satellite correction experiment](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_17_s01_shared_satellite_prototypes/README.md), published to remote main at `321a84cfbfa9d75e79c2febaa46d24b2807a10ef`.

## Target and controls

The baseline is the higher-coverage **family-extension** result: 3,494/4,797 raw GLRT points associated (72.84%). Its largest remaining polynomial fragment by point count is `S01-RX1-CH2-T000`: **80 points**, 240.295709–298.864400 seconds from scan start, spanning **58.568691 seconds**. The prior-regularized orbital method also leaves it unassociated.

S01 starts at **2026-10-16 16:15:42.609910 UTC**. The supplied GPS position is fixed at 37.849061591561885, −122.48574968092912, with the existing 0 m height assumption. Hardware offsets and small drifts for each RX/band, the RF-dependent coefficient, the graph partition, aliases and residual gates are retained. All controls are repeated for `c = 0` and fitted `c`. This is a frequency/identity diagnosis, not a position-accuracy experiment.

The existing candidate family has 12 fragments / 407 points across both receivers. Ten fragments / 284 points pass at the existing common phase; the 80-point target and RX1 CH3 T000 (43 points) fail. Eight fragments have qualifying raw curvature. Linear fragments never estimate any phase, rate, or other calibration parameter.

## The polynomial is sound

| Polynomial degree | All-point RMS, Hz | Penalized score | Retained points |
|---|---:|---:|---:|
| 4 | 120.69 | 73.69 | 80 |
| 3 | 131.81 | 79.29 | 80 |

The quartic wins under the existing complexity/clutter objective, retains every point, and passes the residual-noise screen. Its residual lag-one correlation is 0.155. A cubic also passes the noise screen. This is not an isolated endpoint bending an otherwise linear track.

## Candidate competition

All **1,707** frozen visible-nearby candidates were tested at **601 phases from −15 to +15 seconds**, with unchanged hardware and the same whole-curve constant/alias profiling. Each candidate can choose its own phase. The table ranks by minimum RMS; admissibility still requires visibility, bias and all residual tests.

| Candidate | Causal TLE best RMS, Hz | First later-epoch bank best RMS, Hz |
|---|---:|---:|
| **62811** | **198.97** | **309.18** |
| 69428 | 1,164.08 | 1,151.37 |
| 65387 | 1,916.39 | 1,880.43 |

**No candidate passes all gates in either bank.** NORAD 62811 is a substantially better shape candidate than the alternatives under this model, but these distances are not calibrated identity probabilities. The later bank has first future-epoch elements for 1,671 candidates and explicit causal fallbacks for 36; 62811 itself has genuine later elements.

The competition uses the existing interpolated orbital bank. Direct SGP4 checks of 62811 give 198.94 and 309.23 Hz RMS respectively; the small interpolation differences do not change any conclusion.

## What “right after the measurement” contains

All elements came from the existing read-only Space-Track archive. Selection was fixed before looking at this track: the first post-scan collection, and independently the earliest element epoch after the scan, breaking ties by earliest collection.

| Entry for 62811 | Element epoch, UTC | Archive collection, UTC |
|---|---|---|
| Causal | Oct 15, 22:34:26.875776 | Oct 16, 16:02:13.595712 |
| First collection after S01 | **Same causal elements** | Oct 16, 17:04:36.807915 |
| First actual future-epoch update | Oct 16, 22:01:19.848576 | Oct 17, 05:00:43.978689 |

The first download after the measurement therefore provides no new orbit for this satellite. The first updated orbit is about 5 h 46 min after scan start, and was available in the archive about 12 h 45 min after scan start. It makes this track's phase-only shape worse. Its best individual fit also has a profiled bias of approximately 3,276 Hz in the fitted-c arm, exceeding the 3,000 Hz gate. No best-looking future epoch was selected retrospectively.

## Why a shared satellite slope does not rescue it safely

Direct SGP4 phase profiles use the same ±15 s phase range and a ±20 Hz/s extra satellite-rate box at 11.5 GHz. Each fragment retains its existing Gaussian constant. Family fits cap the contribution of each curve at 50 points. All calibration subsets consist only of raw-curved fragments. The target-only fits are diagnostic and do not satisfy the multi-channel correction ownership requirement.

| Causal model | Phase, s | Extra shared rate, Hz/s | Target RMS, Hz | Target passes? |
|---|---:|---:|---:|---|
| Best phase for target | −0.85 | 0 | 198.94 | No |
| Phase + rate fitted to target alone | −0.45 | +12.53 | 138.27 | Yes, conditionally |
| Phase + rate fitted to all curved family fragments | −0.60 | +7.12 | 151.87 | No |
| Phase + rate fitted to previously accepted curved fragments | −0.70 | +2.16 | 183.62 | No |
| Phase + rate fitted to curved fragments excluding target | −0.70 | +2.20 | 183.24 | No |

The target-only correction makes **four previously passing RX2 fragments fail, totaling 94 points**. It gains the target's 80 points while reducing this family's passing support from 284 to 270 points. This explains why the conservative family-extension prototype retained its earlier state: accepting a target-specific slope would sacrifice established curved support on RX2.

The later TLE can conditionally reach 144.68 Hz RMS for this target with phase +0.80 s and a rate at the **−20 Hz/s boundary**. That boundary fit does not establish a safe family-wide correction either. With the later TLE, corrections learned from the other curved tracks still fail on the target.

![Expected orbit curves, target residuals, and RX1 family residuals](fitted_c/target_and_family.png)

The top panel plots the expected orbit curves, including the explicitly labeled empirical satellite rate where fitted, on a common constant-aligned CFO axis. Constants are profiled once per curve, not separately at each point. The target-only curves are illustrations, not accepted identities. The bottom panel reveals fluctuations shared by multiple RX1 channels.

## A receiver-level clue independent of orbit fitting

Independently subtracting a fourth-degree polynomial from each track leaves fluctuations that correlate across **different satellite candidates on RX1**. Nearest timestamps are matched within 0.3 s, requiring at least 12 matched target timestamps, at least 15 points and a 20 s span. Comparisons are descriptive: samples are temporally dependent, and nearest matching can reuse a reference sample.

| Other RX1 fragment | Candidate NORAD | Matched target timestamps | Quartic-residual correlation |
|---|---:|---:|---:|
| CH1 T006 | 67658 | 35 | 0.790 |
| CH1 T003 | 65627 | 17 | 0.761 |
| CH5 T005 | 69332 | 15 | 0.690 |
| CH6 T002 | 69428 | 22 | 0.406 |

For comparison, same-satellite RX1 CH3 T000 and CH4 T005 give correlations of 0.707 and 0.702 after their independent quartic fits. Overlapping RX2 comparisons in the saved table are much weaker. Because the cross-satellite comparison uses empirical polynomials, no TLE correction was used to manufacture those correlations.

Taking the median reference residual from **all four qualifying curved RX1 tracks nominating other satellites**, with only the fixed RF ratio as gain, supplies a prediction at **64/80 target timestamps**. The target and every 62811 fragment are excluded from that reference estimate. On exactly those same timestamps, target quartic-residual RMS decreases from **116.41 to 89.12 Hz**. No regression coefficient was learned from the target.

![RX1 fluctuations across candidate satellites and conditional fixed-gain transfer](receiver_common_fluctuations.png)

This supports a common RX1 measurement component beyond independent per-point noise. It could arise in the receiver/LNB chain, a common frequency reference, timing, or the CFO estimator. These data do not identify the hardware cause. Independent polynomial detrending removes slow components, so this test **does not resolve the slower satellite-shape disagreement**, and it cannot justify a whole-track association by itself. Some reference satellite labels are only hypotheses, although their measured curves and fluctuations do not depend on those labels.

## Interpretation and next experiment

The strongest current hypothesis is that this track comes from **62811**, with both a receiver-common fluctuation component and a remaining smooth-model discrepancy preventing a defensible accepted match. The first newer TLE does not repair that discrepancy. A single extra satellite slope is insufficient to reconcile the independently observed receiver curves while preserving accepted support.

The next controlled experiment should estimate a low-complexity receiver-common time-dependent error from several simultaneously curved satellite families, with separate RX/band responses if supported. Keep the target and its entire proposed satellite family out of that receiver calibration, then test whether the frozen correction transfers to the complete target curve and the existing RX2 family. Joint orbital corrections still need priors and curved multi-channel ownership; linear tracks can only receive the resulting calibration. Any extension should retain complexity and residual-structure tests and compare both c arms with identical observations, candidates and budgets. A better frequency fit alone does not establish a better location.

## Artifacts and verification

- `target.json`, `polynomial_orders.json`, `tle_provenance.json`: original measurements, polynomial comparison, and exact TLE lines/provenance.
- `{c0,fitted_c}/{past,first_future_epoch}_profiles.json`: full fixed-family SGP4 phase/rate diagnostics, calibration membership, per-fragment residuals and gates.
- `{c0,fitted_c}/{past,first_future_epoch}_identity.{json,npz}`: complete candidate/phase grids and ranked minima.
- `receiver_common_fluctuations.json`: reference policy, all cross-channel comparisons, supported timestamps and fixed-gain prediction.
- `validation.json`, `protocol.json`: point/alias population checks, matched c-arm outcomes, future-bank fallback IDs, exact source hashes, and the 94 points sacrificed by the target-only correction.

All 80 target observation IDs are unique and retained. Both c arms have identical candidate grids and passing-candidate masks; neither admits a phase-only match. Fitted c changes profiled constants but leaves the substantive frequency-shape conclusions unchanged. Eight focused numerical tests passed, including synthetic shared-rate recovery across aliases/RFs, receiver/band hardware application and horizon rejection. All three new research tools pass Ruff. No RF collection, archive write, or localization search was performed.

## Follow-up: track provenance and independent 20-second fits

An instrumented replay of RX1 CH2 reproduces the exact 80-point membership with all four recorded scientific source hashes unchanged. The complete target already exists as one graph proposal **before** finalization and structured repair. Repair receives that same one 80-point model and emits one polynomial piece. Its observation IDs remain unchanged between the primary graph result, append-only recovery, and the later robust polynomial partition. Thus the receiver/band joining stage did not create this track, and there is no later merge of separate fragments in its provenance. A mistaken association during graph discovery remains a possibility to assess from the data, rather than something this provenance alone can rule out.

All points are RX1 CH2. The largest adjacent sampling gap is **1.780 seconds**. Only four other same-channel GLRT detections lie within the full time interval; after allowing the native CFO alias period, the nearest of those is still **56.1 kHz** from the track polynomial. There is no measured nearby alternative branch into which this path visibly switches.

Each fixed 20-second interval was independently fitted with the same degree 1–4, 150 Hz noise, explicit clutter and complexity-penalty comparison. No satellite model, continuity constraint, changed alias, or discarded observation was used in these segment fits.

| Interval, seconds from S01 start | GLRT points | Preferred degree | Independent RMS, Hz | Full quartic RMS on the same points, Hz |
|---|---:|---:|---:|---:|
| 240–260 | 28 | 2 | 138.14 | 129.4 |
| 260–280 | 28 | 3 | 96.29 | 112.5 |
| 280–300 | 24 | 3 | 108.35 | 119.4 |

Every point is retained. The first segment chooses a simpler quadratic even though its RMS is higher than the full-track quartic on those points. The full-track penalized score is **73.69**, versus **83.84** summed over the three independent preferred segment fits, before any additional split penalty. This favors retaining the full polynomial under the existing empirical objective.

![240–260 seconds, raw CFO, enlarged curvature and residuals](segments_20s/segment_240_260.png)

![260–280 seconds, raw CFO, enlarged curvature and residuals](segments_20s/segment_260_280.png)

![280–300 seconds, raw CFO, enlarged curvature and residuals](segments_20s/segment_280_300.png)

The top panels show native CFO and other same-channel detections. The middle panels use the original alias lifts and remove the same straight line from data and both polynomial curves to enlarge curvature. The bottom panels compare empirical polynomial residuals, not satellite residuals.

One GLRT point at **292.468370 seconds** has native CFO −67,768.32 Hz and the frozen alias lift −1, giving −295,041.05 Hz on the track's unwrapped branch. This is explicitly visible in the third plot. Its branch shift is exactly **227,272.73 Hz**, and its unwrapped residual is ordinary in size.

Independent predictions at the arbitrary 260 and 280 second boundaries differ by **+130 Hz** and **−408 Hz**, respectively. The 280 second region merits visual scrutiny. These predictions extrapolate slightly into sampling gaps and are weakly constrained at segment ends. Under a nominal independent 150 Hz noise model, the differences have standard errors of 140 and 161 Hz; the second discrepancy is approximately 2.5 such standard errors. Shared RX fluctuations and model selection are omitted from that nominal calculation. This is not proof of a discontinuity or a wrong join. The full polynomial residual remains unstructured under its current tests.

Exact replay events, all degree comparisons, original IDs, alias exceptions, neighboring detection distances and boundary diagnostics are saved in `segments_20s/results.json`.

## Follow-up: local RMS, truncation and orbital/timing tests

![Native GLRT context across both receivers](native_glrt_context.png)

The native context includes all GLRT in gray and all 62811 candidate fragments in color. The isolated alias point is annotated. The target remains one measured path despite its satellite-model residual mismatch.

![Local RMS and changing residual mean](local_rms_and_mean.png)

RMS to the existing orbit rises from **166 Hz in 240–250 seconds** to **281 Hz in 290–300 seconds**. The last window has a mean error of **+259 Hz** but scatter about that local mean of only **108 Hz**. RMS to the empirical quartic is **97 Hz** in the last window. The late rise is predominantly model bias; the point scatter does not show a corresponding late increase.

A post-hoc truncation proposal requires a 20 second minimum span and at least 20% headroom under every residual-structure limit. It retains the first **53 points**, ending at **276.846583 seconds**, with **140.5 Hz** RMS, and keeps all remaining **27 observation IDs explicitly unassociated**. The longest prefix passing the ordinary gates has 62 points but is only about 2.6% below its closest structure limit. Neither proposal changes the published association or deletes data.

Replaying the complete family-extension state reproduces the baseline exactly in both c arms. Replacing just the target by the 53-point prefix and competing against all **1,707 frozen final candidate states** gives a unique feasible 62811 candidate in each arm, with no other assignments changed. This is a conditional, post-selection proposal; phases for every competing satellite were not independently reoptimized for the shorter fragment. See `orbit_timing/prefix_candidate_competition.json` and `truncation_proposal.json`.

![Conservative truncation proposal and explicit unassociated remainder](orbit_timing/truncation_proposal.png)

Six exact-SGP4 orbital adjustments were tested one at a time with a shared phase: mean motion, inclination, RAAN, the two eccentricity-vector components, and B*. Relative RX1 time offset and RX1 clock rate were also tested. Every model was fitted to the target alone, all eight raw-curved family fragments, and those curved fragments with the target omitted, in both c arms: **60 bounded diagnostic fits**. Hardware, GPS, observations, candidate family labels and search budgets were matched. All final predictions were checked with direct SGP4; maximum interpolation error was **0.189 Hz**. No linear fragment estimated a correction.

| Diagnostic | Target RMS, Hz | Interpretation |
|---|---:|---|
| Best common phase only | 198.7 | Still fails |
| Eccentricity-vector component + phase, target only | 136.9 | Target passes, but 240 previously passing family points fail |
| Mean motion + phase, target only | 142.2 | Target passes, but 53 previously passing family points fail; phase approaches its bound |
| Best eccentricity component + phase, all curved members | 150.8 | Target still fails residual structure |
| RX1 constant clock offset + phase, all curved members | 201.1 | Does not fix the target |
| RX1 clock rate restricted to ±100 ppm + phase, all curved members | 197.7 | Reaches its rate boundary; target still fails |
| RX1 clock rate allowed to ±5000 ppm + phase, all curved members | 141.9 | Target passes and all 284 previously passing family points remain passing |
| Same broad clock-rate model, target omitted from fitting | 168.2 | Target still fails |

The broad all-curved timing fit proposes **−2843.75 ppm** (−0.284375%) for RX1, equivalent to about **171 ms of time-scale compression over 60 seconds**, together with common satellite phase −0.582031 s. The target-omitted fit instead proposes −1156.25 ppm. These are diagnostic boxes, not validated oscillator priors. Relative timing can explain more of the family than an extra correction shared identically across both receivers, but parameter consistency is insufficient to establish a real clock fault.

Applying the all-curved clock proposal to other overlapping curved satellite families while keeping their previously fitted models frozen makes **two accepted fragments / 98 points fail**. It rescues one other 36-point fragment. A full joint recalibration of all satellite phases and receiver timing was not performed, so this conditional transfer failure is a reason to withhold adoption rather than a proof that timing is impossible. Pooled residuals of the seven accepted curved 62811 fragments also retain correlation: 0.383 versus a nominal limit of 0.229 for 304 points.

![Orbital and clock fits, target transfer and other satellite families](orbit_timing/model_comparison.png)

All corresponding per-fragment passing masks agree between c arms. These are frequency-fit sensitivity results at supplied GPS, with no localization-accuracy inference. The current evidence supports a reasonable empirical track and an unresolved shared measurement/model discrepancy. It does not support silently replacing the scan clock or forcing satellite membership. Fourteen focused tests pass, including the existing orbital-invariance controls and new receiver-clock unit/reference/receiver-isolation controls.
