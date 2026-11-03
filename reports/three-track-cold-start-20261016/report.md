# Cold-start recovery and upstream root causes

Scan: `fast8-auto-20261016-161535-99008d35-1-lower`.

This follow-up distinguishes the successful conditional joint-model tests from fresh discovery with test measurements absent. The investigation is not complete: the early-to-late cold fold succeeds, while the reverse fold still fails source selection. These are frequency-prediction results, not geographical accuracy measurements.

## A fresh forward fold recovers all three candidates

The input omits the 63 withheld probe groups before candidate discovery, source generation, calibration and initialization. The 66 target training points remain available. The original export is untouched, and the derived input has its own recorded SHA256. No original full-scan position or fitted calibration initializes this pipeline.

| Target | Training-selected candidate | Withheld points | Cold background + timing search RMS | Cold joint model RMS |
| --- | ---: | ---: | ---: | ---: |
| CH2, 50–75 s | 69433 | 14 | 130.93 Hz | 132.63 Hz |
| CH4, 40–100 s | 69333 | 36 | 135.91 Hz | 143.64 Hz |
| CH2, 170–190 s | 69522 | 13 | 172.53 Hz | 123.45 Hz |

All 63 withheld points are associated with these training-selected candidates in the fitted cold joint model. Applied to the same 4,797 original observations, that model associates 4,214 (87.8%). This whole-scan coverage mixes training and withheld observations; it does not validate every association or establish position accuracy. Candidate selection, calibration and priors differ from the original 1,643-association result, so the progression is not a one-factor ablation.

![Forward and reverse cold temporal tests](01_cold_temporal_transfer.png)

## The apparent band discrepancy depends strongly on calibration

The cold forward pipeline chooses a jointly calibrated B source. Its physical high-minus-low receiver offsets differ from the original Space-Track A source:

| Receiver | Original A contrast | Cold forward B contrast | Difference |
| --- | ---: | ---: | ---: |
| RX1 | −14,767.89 Hz | −18,116.19 Hz | −3,348.30 Hz |
| RX2 | +40,580.99 Hz | +40,526.88 Hz | −54.11 Hz |

The approximately 3.3 kHz RX1 difference is comparable in scale to the original band disagreement. This is a root-cause lead, not an isolated causal measurement: the source also changes calibration coefficients, satellite timings and position jointly.

In this cold calibration basin, the joint model's two fitted lower-band frequency-basis amplitudes are only −0.0248 and +0.0100 seconds. They are much smaller than the approximately −0.95-second coefficient required in the earlier A-based experiment. Removing the extra band terms and refitting from the accepted joint endpoint still predicts late CH2 at 115.52 Hz withheld RMS, with 13/13 points associated. Its 20 fixed RX2 counterpart detections have 209.83 Hz RMS, without fitting their values or adding a satellite-specific frequency correction. The simpler model retains 62/63 target assignments across the forward fold; one CH4 point remains clutter.

Starting the no-band model directly from the earlier cold source loses the early CH2 trajectory, while initializing the same model from the accepted band-model endpoint recovers it. Thus some apparent model differences are optimization-basin differences. Initializations and their additional budgets are recorded separately; the continuation is not a matched-budget proof of superior model complexity.

The evidence does not require a distinct transmitted frequency law to explain the late CH2 discrepancy. It also does not exclude such behavior. A timing-shaped residual observed under one calibration is insufficient to identify a physical clock or transmitter fault.

## The reverse cold fold remains a failure

With the 66 earlier test points removed before discovery, the unmodified pipeline selects a different basin. The training-only candidate searches then produce:

| Target | Selected candidate | Earlier-half withheld RMS |
| --- | ---: | ---: |
| Early CH2 | 69333 | 1,474.83 Hz |
| CH4 | 57149 | 387.56 Hz |
| Late CH2 | 57784 | 2,146.59 Hz |

The alternative accepted A source also fails the training coherence gate for CH4 and late CH2 and does not repair transfer. The investigation therefore has not established reliable cold recovery in both directions.

## A measured loss of track evidence when channels are combined

The reverse CH4 training segment contains 36 points spanning 24.49 seconds with 123.78 Hz raw quadratic RMS. Its reconstructed track has 38 points over 25.91 seconds and ranks 20th by span among receiver-zero eligible tracks. The combined view retains only the 12 longest tracks per receiver. Consequently all 36 target points are represented in the lower-band bootstrap and none in the combined-view bootstrap.

The short CH2 training segments are absent from bootstrap evidence as well. The detailed audit distinguishes missing raw tracklets from the later bootstrap filter: the reverse late-CH2 segment is present in a 20-point raw track spanning 13.85 seconds, which fails the 15-second bootstrap requirement. Other short CH2 segments are not reconstructed as tracklets at all. They cannot all be attributed to the final length filter.

![Target training-point coverage in bootstrap tracks](02_bootstrap_target_coverage.png)

A controlled experiment replaces the combined-view bootstrap with the union of the unchanged lower- and upper-band bootstrap tracks. Observations and training-input bytes remain identical. Bootstrap tracks increase from 24 to 48, retaining roughly 1,830 rather than 1,100 observation rows. This change alone fails: withheld RMS worsens in both folds. Preserving more tracks without controlling their influence does not solve source generation.

## Background assignment checks

The earlier conditional band-term experiment loses three initially high-posterior assignments to 69522 around 244–251 seconds. Under the cold forward calibration, those same points are assigned to 62811 with approximately 91, 146 and −115 Hz residuals. The new assignment has 25 nearby CH2 matches spanning 18.45 seconds and 41 CH3 matches spanning 28.40 seconds. This is stronger trajectory context than the isolated earlier matches, although no independent identity truth is available. A high pointwise satellite posterior alone is not proof of a correct identity.

## Original rejected B checkpoint

The original complete-data B fit has objective 50,962 versus 58,410 for the accepted A fit, but fails the 0.001 stationarity gate at 0.0137. An additional bounded continuation still fails at 0.00810 and does not recover the three trajectories consistently. Its 3,915 associated observations include a different candidate for the CH4 trajectory and no late-CH2 associations. It remains rejected. Neither its lower objective nor its higher coverage justifies bypassing the numerical or scientific checks.

The reverse cold pipeline refines only one of its five accepted B donors in the longer shared model. The four discarded donors were therefore each given the same 60-second fitter and 65-second total allowance. All four converged under the unchanged strict audit, in approximately 27–31 seconds, but none recovers all three trajectories in training-only full-catalogue candidate searches. Their early-CH2/CH4/late-CH2 withheld RMS values are respectively 892/2,250/2,892 Hz; 4,869/6,344/657 Hz; 5,034/6,462/823 Hz; and 928/1,534/737 Hz. Choosing another existing B donor is insufficient to repair the failure. The initial adapter setup omitted the shared model's detectability tail and failed before optimization; that setup was corrected before these fits.

## Supplied training-track groups also fail to repair discovery

Two bounded cold runs supplied only the training portions of the three predeclared user-identified trajectory groups to bootstrap discovery. No satellite identity, frequency correction, timing correction or held measurement was supplied. Each training group had to have at least eight points, span at least four seconds, and pass a 400 Hz raw quadratic-residual gate. Existing overlapping bootstrap groups were replaced to avoid duplicate use in source proposals. Observations were unchanged.

This tests use of the supplied trajectory grouping; it is not a test of blind track extraction. Both pipelines completed with accepted numerical endpoints, in 339 and 355 seconds respectively. They still failed the target transfer checks:

| Training fold | Early CH2 withheld RMS | CH4 withheld RMS | Late CH2 withheld RMS |
| --- | ---: | ---: | ---: |
| Earlier halves | 4,920 Hz | 6,180 Hz | 1,732 Hz |
| Later halves | 2,027 Hz | 421 Hz | 503 Hz |

The missing-track evidence is a genuine upstream defect, but supplying those groups alone is insufficient to explain or repair the wrong calibration and source basin. The next discriminator should examine how coherent trajectories influence source proposals and how receiver band contrasts are initialized and refined. Adding satellite-specific corrections or more unweighted tracks is not supported as a complete fix by these results.

## Coherent identities do not remove calibration ambiguity

A further training-only experiment requires one satellite identity for each of the three provided training groups and fits a single extra RX1 lower-band offset and drift shared across them. It searches all 1,035 regional candidates with the same ±5-second timing range and 2-second timing prior. The shared offset has a 4,000 Hz prior and ±8,000 Hz bound; drift has a 20 Hz/s prior and ±40 Hz/s bound. All held measurements remain absent from parameter and candidate selection.

At the original cold forward position, this preserves candidates 69433/69333/69522 and gives withheld RMS of 160/193/173 Hz. At the original reverse position, early CH2 fails its training gate and the three withheld errors are 1,731/819/225 Hz. A common linear receiver adjustment alone therefore does not repair the reverse fold.

The same reverse-fold search was also evaluated at a predeclared nine-point regional grid: east and north coordinates independently take −150, 0 and +150 km relative to the configured prior. Among those nine points, the smallest training objective occurs at the prior center, where all three candidates pass the existing training gate of RMS ≤375 Hz and an alternative-identity score gap ≥20. Yet the candidates are 65398/47357/59370, with training RMS 132/209/211 Hz and withheld RMS 517/2,205/434 Hz. No held score chooses this point or its identities.

This is a concrete counterexample to treating a good short-track fit and a large candidate score gap as sufficient identification when calibration and position are uncertain. The gap is conditional on the chosen position and calibration; it is not a globally calibrated probability of correct identity. The nine-point search remains a failed diagnostic and is not a proposed localization solution. Qualification must check predictions on independent time segments or stronger background trajectory constraints before accepting these groups.

![Training fit versus withheld prediction across the nine-point reverse-fold diagnostic](03_coherent_training_vs_test.png)

## Free receiver band contrasts do not repair the reverse fold

The next matched experiment starts from the reverse cold endpoint, compresses every initial satellite timing to ±3 seconds, applies a common 0.5-second relative timing prior, and compares free versus frozen receiver high-minus-low offsets. The free and fixed seed predictions and objectives agree exactly before changing the timing prior. Observation sets, selected candidate bank, other priors, local position domain and fitter allowances are matched. No target identity or target-specific correction is supplied. Both fitted-`c` and `c = 0` arms receive up to two 60-second fitter / 65-second total allowances; converged runs can stop earlier.

| Band contrast | RF arm | Strict endpoint accepted | Earlier CH2 RMS | CH4 RMS | Late CH2 RMS |
| --- | --- | --- | ---: | ---: | ---: |
| Frozen | Fitted `c` | Yes | 1,659 Hz | 299 Hz | 231 Hz |
| Free | Fitted `c` | Yes | 1,613 Hz | 399 Hz | 2,215 Hz |
| Frozen | `c = 0` control | Yes | 1,574 Hz | 145 Hz | 2,344 Hz |
| Free | `c = 0` control | No | Not evaluated | Not evaluated | Not evaluated |

The free-zero endpoint remains rejected at stationarity 0.002456 versus the unchanged 0.001 gate. Repeating the bounded allowance leaves it unchanged; no threshold is relaxed. Its training objective is retained as a rejected diagnostic, not an accepted model comparison.

The frozen fitted-`c` endpoint's training NLL is 57,255.93 versus 57,936.98 for the frozen zero control. This better frequency score does not establish better localization or a uniformly better withheld fit. CH4 and late CH2 can predict well under alternative identities: the frozen fitted-`c` endpoint selects 57149 and 65627, while the successful forward endpoint selects 69333 and 69522. No independent identity or position truth is asserted for either set. Free fitted `c` selects 69333/57149/57784 for early CH2/CH4/late CH2 and does not recover all three consistently.

![Reverse-fold withheld frequency errors after free or frozen band refinement](04_band_contrast_controls.png)

The three lowest-objective low-band discovery calibrations were also checked before their B-donor refinement, ranked exclusively by the original training low-band objective. Their early-CH2/CH4/late-CH2 withheld errors are 1,695/174/192 Hz; 2,559/2,303/2,070 Hz; and 4,851/6,566/543 Hz. None repairs all three groups.

These failures narrow the next model change. The shared background likelihood allows each point to choose a different satellite or clutter. Supplying a track to bootstrap does not preserve its identity during final fitting. A [subsequent grouped-track experiment](../three-track-grouped-fit-20261016/report.md) now tests one shared latent identity per supplied training group, candidate retention and timing initialization, with the original outer withheld halves and no supplied satellite labels. It also identifies that candidate 69333 was proposed at seven reverse-fold discovery points but discarded from the final candidate bank. That follow-up still does not recover all three trajectories in both folds.

All terminal results, derivative audits, input derivations and source code used in this snapshot are retained beside the figures. The report manifest covers the copied evidence. A [checkpoint replay capsule](../three-track-recovery-replay-20261016/report.md) now reconstructs the original training inputs from the hash-verified export and independently reproduces both cold folds and the two successful forward joint checkpoints without old temporary investigation files. This reproduces saved models, not fresh discovery. No production code, automatic scan job or recording has been changed.
