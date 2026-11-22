# Recovering deployed endpoints from exact native margins

Restoring the archived deployed fractional margins at the radio-noise calculation recovered **exact deployed coordinates in both calibration arms** on DS30-0374 and DS30-0008. All four original coordinate differences exceeded the `1e-8 km` gate. The same replay reproduced the deployed Doppler residuals, owners and optimizer paths. The off-site southern control already matched deployment and stayed exact. This is a saved-input crossover using native measurements from the same recordings. [Bound measurements and gate outcomes](measurements/solver-deployed-margin-recovery.json)

## First numerical divergence

The archived `ad417…` and `977e…` native solver publications have identical coordinates and RMS within each arm and build on both physical recordings. The `4457…` longitude successor previously replayed the spectral parent’s southern result exactly. On all three saved input pairs, the selected ranks, integer and fractional epochs, carrier frequencies, winning observation identities, and complete Graph tracks matched. The native exact-pilot and rolled-control scores changed at the last few bits. Subtracting the two saved candidate scores reproduces the candidate margin on every selected row and recovers the deployed margin only where it already agrees. [Physical receipts](terminal-guard-publication.md#physical-recordings-from-one-roof) · [Longitude replay](measurements/spectral-wrapped-longitude-south-solve.json)

| Published input | Changed fractional margins | Largest margin change | Chosen noise model | Changed per-observation σ | Largest σ change |
|---|---:|---:|---|---:|---:|
| DS30-0374 | 3,978 / 4,157 | 2.245 × 10⁻¹³ | Heteroscedastic | 4,157 / 4,157 | 8.178 × 10⁻⁶ Hz |
| DS30-0008 | 6,679 / 7,016 | 2.336 × 10⁻¹³ | Heteroscedastic | 7,016 / 7,016 | 2.958 × 10⁻⁵ Hz |
| Southern containing | 446 / 456 | 2.154 × 10⁻¹⁴ | Constant 40 Hz | 0 / 456 | 0 Hz |

The released variance estimator fits the Graph residuals to `floor + strength / margin` and uses its original BIC comparison. Changing only the selected margins changed the fitted noise in both physical recordings before any position fit. Deployment and candidate chose the same model class on each input. Restoring the deployed margins recovered the entire noise record, including its per-observation scales and BIC, exactly. A final optimizer replay using the candidate’s scales still evaluates the altered likelihood. A replay beginning at noise preparation can recover the released calculation when the exact native margins are supplied. [Released variance fit](../../../src/leo/analysis/localization_v3/noise.py) · [Position input weights](../../../src/leo/analysis/localization_v3/position.py)

## Native solver crossover

The adapter binds the two saved documents to the same raw authority and compares every winning observation field other than margin. It supplies the archived deployed margins only at `estimate_noise`. The normal native path then reruns initial, conservative, history, signed, cavity and selected-evidence calculations with the original offer, detector chronology, catalogue and fitted or fixed-zero settings. The physical replays use `977e…` and the southern replay uses `4457…`. No surveyed position, coordinate adjustment or late optimizer warm start enters the crossover. [Replay adapter](solver_deployed_margin_trial.py)

| Saved input | Original displacement, fixed-zero / fitted | After margin replay | Owners per arm | Complete saved solve CPU / elapsed |
|---|---:|---:|---:|---:|
| DS30-0374 | 2.128 / 5.123 × 10⁻⁸ km | 0 / 0 km | 2,905 | 22.897 / 24.245 s |
| DS30-0008 | 3.127 / 1.754 × 10⁻⁸ km | 0 / 0 km | 4,472 | 55.907 / 56.732 s |
| Southern containing | 0 / 0 km | 0 / 0 km | 266 | 4.827 / 4.929 s |

Both coordinates and RMS matched exactly in each arm, along with its owner digest, full recorded path and zero endpoint objective-replay difference. The physical grids used all 179 deployed point coordinates and failure fields, with at most `7.276e-12` change in any score in either arm. Their digests still differ in point scores and nuisance-model metadata under the experimental posterior handoff. The southern grid matched exactly. The clocks measure complete saved solver execution with the restored inputs. [Numerical comparison](measurements/solver-deployed-margin-recovery.json)

## Exact margin production

The earlier native repair retained the pre-fractional CFO and chosen epoch through continuation, then used the deployed absolute-phase fractional correlator for the selected exact-pilot and rolled-control scores. It recovered every score field on 53 measured physical selections in **33.17–33.34 ms**. At that rate, repairing every selection would add about **2.60–2.62 CPU seconds on DS30-0374** and **4.39–4.41 on DS30-0008**. These are projections from the archived component timing. Such a receiver change would need to verify seed and epoch parity and selection gates across each complete input. The saved score operands alone cannot supply the missing released margins. [Measured native score repair](receiver-fractional-score-consumers.md#recovering-the-stock-score-only-on-selection) · [Native lineage](receiver-cfo-lineage.md)

## Reproduction

Run the saved preparation diagnostic `solver_deployed_margin_trial.py prep NEW_OUTPUT PAIR...` with the checkout storage adapter and the released-equivalent track and noise code. For each pair, stage the `baseline` and `candidate` documents and original offer from `read_inputs`. Run `cross-worker CANDIDATE BASELINE SPEC ARCHIVE OFFER NEW_TERMINAL` with the corresponding frozen bundle first on `PYTHONPATH`. All numerical work used the low-priority Gauss lock, CPU 2, and one thread. The component test checks exact support binding and refusal to replace margins across changed observations. [Component test](../../../tests/pipeline_eval/test_solver_deployed_margin_trial.py)
