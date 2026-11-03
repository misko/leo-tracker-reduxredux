# Shared unknown site across DSX01: feasibility review

**Pooling an unknown site is an established approach in this repository, but I found no completed fit sharing one unknown site across these five DSX01 recordings.** The public metadata supports common hardware, not independently verified absence of receiver movement. A five-scan shared-site calculation would therefore be a conditional static-receiver experiment, not an already justified replacement for independent localization. No objective, gradient, propagation, optimization or reference-coordinate lookup was run for this review; five public `SharedFastScanStore.plot_evidence` reads verified the frozen input/terminal bindings.

## What was already tested

- [September26 three-scan joint-location prototype](../2026_09_26_joint_location_prototype/REPORT.md) fitted/ranked an unknown common site with independent per-scan timing/identities. Its conditional proposal inventory and historical observation conditioning limit the reported improvements. The report already requires a receiver-stationarity check for live pooling.
- [September28 union-panel experiment](../2026_09_28_union_panels/README.md) estimated one unknown site over45 recordings, retaining scan-local timing/offsets. Geographic agreement and held frequency score did not improve together consistently.
- [September29 joint72](../2026_09_29_joint72/README.md) used one geographic site and72 independent scan timings. It retained separate dataset fits after the joint estimate failed to improve outside-scan prediction overall. Unchanged physical installation was explicitly an assumption.
- [October1 quad protocol](../2026_10_01_quad_development/PROTOCOL.md) already specifies the requested structural form: one common unknown east/north point with independent scan clocks, receiver drifts, satellite epochs and associations, correct scan-local UTC origins and metadata-selected groups. [Completed recursive quad results](../2026_10_01_quad_development/FULL_RECURSIVE_QUAD_RESULTS.md) retain multiple converged modes and failures rather than treating pooling as a general solution. Those are other corpora and likelihoods, not DSX01 evidence.

The October16–17 DSX01 reports instead fit each source independently. Their wording “shared position” refers to a common position within one scan, and “all-five joint-band” means the same band-refitting policy run separately on five scans. The old three-track common-site diagnostics also share a site within one recording, often with manually selected segments; they are not the proposed five-recording estimator. This was a targeted report search, not a claim to exhaust every historical artifact.

## Actual hardware/session authority

All five public tracking inputs name radio `1040005e0b100007100010000bf33a5d4d`, sample rate2,500,000Hz and adaptive capture mode. Their acquisition sessions and continuous-IIO generation tokens are distinct:

| Source | Capture UTC, October16 | Stream generation suffix | Original selected / regional IDs |
|---|---|---|---:|
| S01 | 16:15:42.610–16:20:42.547 | `39e50ebdda1cd2ae` | 46 /987 |
| S02 | 21:01:30.998–21:06:30.960 | `69c12e65d104b445` | 51 /855 |
| S03 | 21:31:46.550–21:36:46.500 | `418d568c79914a91` | 40 /845 |
| S04 | 22:02:02.827–22:07:02.787 | `095f486892462a97` | 46 /880 |
| S05 | 22:32:17.829–22:37:17.757 | `2dc6cc9df5c3e34f` | 32 /821 |

Total capture duration is1499.738218s (about25min), over6.359763h from first start to last end. S02–S05 start roughly30min apart; S01 is separated from S02 by several hours. Different generation tokens identify acquisition boundaries; they prove neither motion nor stationarity. The clocks use the public host-bracket/device-counter timing reconstruction, not continuous counter authority across these separate generations.

Public source metadata has radio/session/generation, capture times/mode/rate, probes, manifest digests and timing. It contains no stationarity, motion, pose or installation-continuity field. The existing [causal calibration inventory](../2026_10_17_dsx01_iteration3/calibration/donor_manifest.json) binds the same metadata and records lower/upper RF mappings as hypotheses. Same radio/rate is compatible with a fixed installation but cannot prove that it remained fixed for six hours. No configured station file or geographic reference was read or used to form groups.

Missing motion fields do not make pooling impossible or imply that the receiver moved. A fixed-deployment record, installation log or validity interval bound to this radio could independently support an explicit stationary-installation assumption without using its coordinates. That authority was not inspected here; these inputs alone do not supply it. Research can still declare static location as an assumption and test its consequences, while keeping that distinction from observed motion truth.

## Coordinate and time compatibility

The five original terminal priors are identical: the same250km regional disk, altitude0m and geographic origin. Thus the public `regional_position_score.coordinates/observer` maps an identical east/north vector to the same receiver site in all five contexts. A shared **unknown** two-coordinate parameter is mathematically feasible without introducing any known-site seed. It reduces ten independent site coordinates to two while retaining independent scan nuisance blocks.

Keep each scan's original observation times, actual RF, ephemeris bank, capture UTC origin and calibration-centering frame. Do not concatenate scan-relative seconds or reuse one scan's bank at another epoch. Identical hardware does not justify sharing receiver affine/RF calibration, band offsets, residual clocks, q or fitted orbital timing. Regional domain/position constraints are common; scan-specific nuisance priors are each counted once. Any later fitted-c study still requires a matched all-c-zero arm.

The existing [five-source identifiability audit](../2026_10_17_dsx01_iteration7/identifiability/README.md) shows that calibration plus independent satellite timings absorb99.48–99.78% of the positive local spatial-frequency information trace. Its weak directions differ across scans, so pooling could in principle help; this review has not computed pooled information, global mode consistency or a joint objective. Those local surrogates are not covariance, movement evidence or identity confidence.

## Candidate coverage limits

The original selected-bank sizes sum to215 and their union also has215 IDs: **no selected satellite ID occurs in two of the five banks**. Shared site geometry does not require repeated emitters, but there is no measured repeated-ID timing constraint here. Every q/timing coordinate would remain scan-local in the proposed model.

This count is strictly about the five original selected banks, not overlap of their much larger regional catalogues. It does not establish disjoint physical emitter populations: selection can omit candidates and fitted labels are not identity truth.

Pooling cannot create a candidate missing from a scan's selected bank. The [S03 half-forecast diagnosis](../2026_10_17_dsx01_iteration5/cold_prediction_diagnosis/README.md) found1190/1410 original held assignments had their full-data winner absent from the25-ID early-selected bank. That is an explicit descriptive ceiling relative to full-data-conditioned labels, not proof of true identities or of omissions in every full-recording bank. The [metadata-only S03 bank](../2026_10_17_dsx01_iteration5/metadata_bank/README.md) contained845 potentially visible IDs and covered those old labels after freezing, but was never a scored recovery model and has no per-transmitter RF-support authority.

Existing banks therefore do **not** prevent a meaningful *conditional* shared-site sensitivity test; they do prevent calling it candidate-complete generic recovery. A common site might suppress incompatible geographic modes, or merely force a compromise among incomplete/wrong identity basins. Enlarging to hundreds of independent free q/timing lines would be a separate population/selection model, not a prerequisite silently added to this pooling test.

## Recommendation

Do not rediscover multi-scan pooling or launch a five-scan campaign from hardware identity alone. First obtain independent installation/movement authority, or explicitly retain static location as an unverified modeling assumption. If root subsequently authorizes a small conditional probe, change only the shared unknown site versus independent sites, with identical per-scan observations, frozen candidate eligibility, nuisance freedom, matched c arms and counted compute; preserve every source's held frequency/identity tradeoffs. One pooled site is one result, not five independent successes. No shared-site implementation or fit is authorized by this review.
