# Merged-track satellite association: DS22 transfer and position failure

The active goal remains **unachieved**: implement satellite association over the new track approaches, evaluate DS22 and DSX01, and verify horizontal position error below 0.5 km. The current cold position pilot is about146–148km from the supplied reference. Increased fixed-site association counts are not localization success.

This iteration evaluates every one of the **68 DS22 fast recordings with a sealed tracking input**, and all five frozen DSX01 scans. DS22 still has68 adaptive recordings without an implemented observation adapter here, plus one fast recording without a pinned tracking export. Every one of137 DS22 members remains in the coverage ledger. No unavailable recording is silently excluded or counted as successful. No new RF was collected.

## Track construction and merging

DS22 contains243,085 gate-passing maximum-margin GLRT winners in these68 fast exports. One physical probe contributes at most one winner. Their sealed snapshot digests and UTC-bracket/device-counter timing are checked. The frozen S01-selected Graph policy is transferred without retuning: degree≤4,150Hz noise scale,450Hz residual gate,8,000Hz/s physical slope cap,4 points per coefficient and6-second minimum span. This is the primary Graph policy; DSX01 reuses its earlier frozen recovered Graph memberships, which had an additional recovery pass. Cross-dataset differences therefore are not a controlled effect of the tracker policy.

Graph assigns216,039/243,085 points (**88.87%**) into7,120 fragments. Curved-only trimmed calibration and polynomial fusion reduce this to6,123 components, without dropping their points. The remaining27,046 gated winners stay in the evaluation denominator. Calibration uses only pairs with measured active curvature, not linear fragments; native drift is capped at5Hz/s. These are exploratory curve correspondences, not physical emitter truth.

![Track coverage](track-coverage.png)

The full137-member accounting is in [cohort/coverage.csv](cohort/coverage.csv). Its statuses are {'tracks_evaluated': 68, 'adaptive_observation_adapter_unavailable': 68, 'no_pinned_tracking_input': 1}. All68 fast exports name the same radio identifier; transferring the supplied station position to DS22 assumes a static installation. Radio identity alone does not independently prove absence of movement.

## Association model and controlled RF ablation

For each scan, retain four receiver×band constants and four small linear drifts: RX1-low, RX1-high, RX2-low and RX2-high. Drifts have a zero-centered2Hz/s Gaussian preference and a hard±5Hz/s limit. There is no one-offset-for-all-DSX01 assumption. Only individually curved fragments vote on hardware calibration, including when a linear member shares a merged component with a curved member.

The hardware-only arm has no component bias. The new arm adds **one native-Hz constant per whole component**, with a zero-centered1,000Hz Gaussian prior. A shared component bias cannot remove slope, curvature, or a discrepancy between member receivers/channels. Its branch-profiled score includes the Gaussian quadratic penalty and the log-determinant term log(1+n*tau²/sigma²). Native integer aliases are profiled per original fragment. The result is a bounded robust research score, not a normalized wrapped joint likelihood or identity posterior.

Actual RF scales the physical Doppler prediction. An optional scan-shared RF coefficient c is evaluated as a matched c=0/fitted-c ablation. Within each grouping/bias arm, observations, candidates, priors, classification checks and maximum160 discovery-seed budget are identical. The bias0 case algebraically nests the hardware-only score. Fewer seeds may satisfy the physical eligibility gates. The Gaussian prior supplies a centering assumption; these fitted offsets are not independent physical clock measurements.

Satellite candidates come from the newest eligible past Space-Track element per NORAD, with both collection and element epoch before the scan UTC bracket, within48hours. Preparation uses the broad regional center(37.5,-122.0), radius250km, and a conservative horizon guard; it does not select candidates using the supplied evaluation GPS. SGP4 is sampled every second and interpolated. The maximum checked interpolation discrepancy across these68 banks is **0.447Hz at11.5GHz**, over96 metadata-selected times and five declared regional sites per recording; this is a sampled qualification, not a uniform analytic error bound. UTC approximates UT1; polar motion is omitted.

Fixed-site association is evaluated at the supplied **37.849061591561885,-122.48574968092912**, assumed0m WGS84 ellipsoidal height. Recorded RF/LNB assignments remain hypotheses; nominal tuner correction is assumed zero in this portable replay. Above-horizon membership is required at every component observation. Compatibility requires≤450Hz RMS, a bias within3 prior sigmas, and the existing per-fragment residual mean/slope/quadratic/step/autocorrelation screen. No independent satellite IDs are available. These are **frequency-compatible candidates**, not verified satellite associations.

## Complete available-input association results

DS22 percentages below use all243,085 available fast gated winners, including Graph-unresolved points. DSX01 percentages use all20,084 original winning points; its frozen Graph population contains18,338. Counts are not percentages of unknown/unavailable adaptive observations.

| Dataset | Matching unit | RF arm | Bias sigma Hz | Cases | Input units | Compatible units | Compatible points | % gated winners | Points / compatible unit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DS22 fast | Graph fragments | c=0 | 0 | 68 | 7120 | 98 | 2137 | 0.88% | 21.81 |
| DS22 fast | Graph fragments | c=0 | 1000 | 68 | 7120 | 1252 | 25402 | 10.45% | 20.29 |
| DS22 fast | Graph fragments | fitted c | 0 | 68 | 7120 | 126 | 2973 | 1.22% | 23.60 |
| DS22 fast | Graph fragments | fitted c | 1000 | 68 | 7120 | 1251 | 25371 | 10.44% | 20.28 |
| DS22 fast | hard merged | c=0 | 0 | 68 | 6123 | 66 | 1437 | 0.59% | 21.77 |
| DS22 fast | hard merged | c=0 | 1000 | 68 | 6123 | 890 | 18263 | 7.51% | 20.52 |
| DS22 fast | hard merged | fitted c | 0 | 68 | 6123 | 84 | 2227 | 0.92% | 26.51 |
| DS22 fast | hard merged | fitted c | 1000 | 68 | 6123 | 909 | 19665 | 8.09% | 21.63 |
| DSX01 | Graph fragments | c=0 | 0 | 5 | 676 | 22 | 506 | 2.52% | 23.00 |
| DSX01 | Graph fragments | c=0 | 1000 | 5 | 676 | 193 | 3610 | 17.97% | 18.70 |
| DSX01 | Graph fragments | fitted c | 0 | 5 | 676 | 20 | 441 | 2.20% | 22.05 |
| DSX01 | Graph fragments | fitted c | 1000 | 5 | 676 | 194 | 3621 | 18.03% | 18.66 |
| DSX01 | hard merged | c=0 | 0 | 5 | 456 | 9 | 202 | 1.01% | 22.44 |
| DSX01 | hard merged | c=0 | 1000 | 5 | 456 | 74 | 1658 | 8.26% | 22.41 |
| DSX01 | hard merged | fitted c | 0 | 5 | 456 | 10 | 232 | 1.16% | 23.20 |
| DSX01 | hard merged | fitted c | 1000 | 5 | 456 | 80 | 2081 | 10.36% | 26.01 |

![Association coverage](association-coverage.png)

The additional constant-bias model substantially increases admitted point counts. Hard polynomial pre-merging still loses coverage relative to fragment matching. This comparison includes different fitted nuisance optima, so it does not uniquely establish that every lost component was a wrong polynomial join. It does establish that hard pre-merging is not a safe replacement in the current pipeline. This iteration has not yet qualified a physical identity false-discovery rate or shown that larger counts are correct.

## Safer identity-guided consolidation

The alternative freezes the unmerged fit's calibration and identity proposals, then considers only equal-NORAD fragments that overlap or are within10seconds. A join must improve the integrated Gaussian constant-bias score and pass all original-fragment residual checks with one shared bias. Different identities, incompatible biases, discontinuous residuals and long gaps remain separate. Failed joins retain both inputs; the component asserts exact observation ownership and zero points dropped. No linear track recalibrates a hardware offset or drift in this step.

| Dataset | RF arm | Input candidate fragments | Consolidated groups | Retained candidate points | Points dropped | Points / group |
| --- | --- | --- | --- | --- | --- | --- |
| DS22 fast | c=0 | 1252 | 1133 | 25402 | 0 | 22.42 |
| DS22 fast | fitted c | 1251 | 1132 | 25371 | 0 | 22.41 |
| DSX01 | c=0 | 193 | 166 | 3610 | 0 | 21.75 |
| DSX01 | fitted c | 194 | 166 | 3621 | 0 | 21.81 |

Thus the fitted-c DS22 candidate population retains25,371 points while reducing1,251 candidate fragments to1,132 groups. DSX01 retains3,621 points while reducing194 fragments to166 groups. This is a useful complexity reduction with a coverage-preservation invariant; it does not independently confirm those candidate labels. Identity-guided consolidation is downstream of fragment matching, while hard polynomial pre-merging was upstream. Their compute budgets and resulting units are not identical.

## Actual position error: four unsuccessful cold pilots

The predeclared pilot is DS22-001, the first available recording by capture time. Search starts from nine fixed regional grid points, independent of the supplied GPS. It reassigns satellites and refits scan hardware at every geography; it does not reuse fixed-site satellite identities. Discovery uses at most eight actual time-spread observations per original fragment, retaining measured curvature eligibility from all raw points. It is a discovery subset, not a held-data validation split. The best four discovered locations are reranked with predictions and component statistics recomputed on all3,510 original Graph points and the full160-seed calibration allocation. The geographic score uses the fixed actively-curved component subset; linear fragments do not calibrate hardware.

Both c arms share the same65-geography maximum, same discovery subset, four-seed discovery allocation, component-bias setting, priors and candidate bank. Up to two axial moves per refinement scale are allowed. This bounded surrogate search is neither globally certified nor a proven local optimum. The endpoint is written before the evaluation coordinate is consumed. Coordinate error is in kilometres; it is not inferred from the frequency score.

| Bias sigma Hz | RF arm | Discovery geographies | Full-data finalists | Estimated latitude | Estimated longitude | Error km | Below0.5km |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | c0 | 41 | 4 | 37.536036 | -120.869119 | 146.440 | False |
| 0 | fitted_c | 38 | 4 | 37.536036 | -120.866288 | 146.682 | False |
| 1000 | c0 | 39 | 4 | 37.493243 | -120.867704 | 147.803 | False |
| 1000 | fitted_c | 39 | 4 | 37.493243 | -120.867704 | 147.803 | False |

![Position error](position-error.png)

All four endpoints fail the0.5km target by a large margin. The component-bias model's fixed-site frequency-coverage gain does not translate into geographic accuracy. No position error has yet been evaluated for the other67 available DS22 fast recordings or the69 unavailable members in this iteration. The first full-row search exceeded its180-second compute cap in fitted-c; its paired c0 attempt was terminated after that cost failure. Those unsuccessful attempts are preserved in [position_full_row_attempt](position_full_row_attempt), not relabeled as valid endpoints. The compressed-discovery search above is a changed algorithm, followed by full-data scoring.

## What changes next

The goal remains active. Priorities are to move the geographic objective onto the coverage-preserving association/merge path, test physically RF-proportional versus native component biases with explicit gauge assumptions, and check competing identity modes before expanding more position fits. A common unknown site across independently supported static scans could constrain false single-scan modes, while keeping each scan's hardware and timing separate. Neither option is established by the present results. Causal orbital-timing uncertainty and the nominal RF correction also need qualification before claiming sub-kilometre accuracy.

The68 adaptive members and missing fast export remain actual scope gaps. They need an existing-data observation adapter or an explicit evaluation failure, not removal from DS22. The new orbit-state port supports geographic evaluation without recollecting RF or importing either reference repository. Subsequent c-dependent analyses must continue to retain matched c=0 controls and report position errors separately.

## Evidence and reproduction

- [All per-record association summaries](per-case-association.csv), [aggregate table](aggregate-association.csv), [DS22 execution](catalogue/execution.json), [DSX01 execution](dsx01_catalogue/execution.json).
- [DS22 consolidation](consolidated/summary.json), [DSX01 consolidation](dsx01_consolidated/summary.json), and their original-fragment membership files retain every point.
- [Hardware-only position pilots](position_hardware_only), [component-bias position pilots](position_pilot), their fit hashes, full-data finalists and complete search traces remain available.
- `tools/evaluate_ds22_merged_tracks.py` transfers the track policy; `tools/associate_merged_track_catalogue.py` prepares orbits and runs matched associations; `tools/run_merged_catalogue_cohort.py` bounds each recording stage; `tools/consolidate_catalogue_matches.py` performs lossless candidate consolidation; `tools/localize_merged_track_catalogue.py` performs the cold regional pilot.

The component tests cover probe ownership, native aliases, no extrapolation, Doppler sign/carrier scaling, bias0 nesting, shared-bias penalties, retained slope errors, incompatible members, fixed grouping/c populations, lossless consolidation, failed/unavailable member accounting, response-blind time subsets and regional search/error units. No golden fixture changed. The final targeted suite contains41 passing cases including the existing Graph and DSX01 fixed-site guards. Static checks pass on the new sources.

Source snapshots are provenance copies under `code_snapshot`; runtime imports remain the current repository. Frozen TLE exports are copied under `orbit_elements`; matrix caches remain outside the report and are hash-bound by their preparation receipts. Input tracking exports remain the sealed DS22 snapshots. [artifact_manifest.json](artifact_manifest.json) binds this report's files. No production model is promoted and the goal is not marked complete.
