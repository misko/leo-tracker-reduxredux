# Why two DS30-0402 fragments failed their cumulative gates

The 61 lost NORAD 58377 observations are a **point-mask effect**. Both intact cumulative fits pass on the original selected 61 observations when the final observation is removed from the gate, with the posterior held fixed. The 48 lost curved observations for NORAD 62735 depend on the **surrounding calibration context**. Changing to the named position and phase reference alone leaves the fixed-zero failure in place if the larger cumulative early roster still supplies calibration. The named roster passes under either position and phase source. The compared point-noise and family-power arrays have no effect on either finding on their matched support. [Frozen protocol](fragment-cross-0402-protocol.md) · [Sealed matrix, gate vectors and clocks](measurements/fragment-cross-0402.json.gz)

## The 58377 tail observation determines the step decision

These rows reapply the original gate to fixed posterior predictions. The 61 rows are the exact chronological subset verified by observation ID.

| Condition | Fixed-zero step z | Fitted-c step z | Local result, both arms |
| --- | ---: | ---: | --- |
| Cumulative intact posterior, all 62 observations | 4.094 | 4.104 | Fail |
| Same cumulative posterior, first 61 observations | 2.834 | 2.846 | Pass |
| Named posterior, original 61 observations | 3.116 | 3.112 | Pass |
| Same named posterior, append original observation 62 | 4.298 | 4.296 | Fail |

The step cutoff is 4. Conditional testing also preserves the original mean and slope cutoffs of 3, quadratic BIC gain cutoff of 10, lag-one limit of 4/√n, 450 Hz RMS and original profile, bias, alias and horizon checks. Keeping the 61-point gate scope constant, all sixteen roster, position/phase and supported weight contrasts clear the gate. In the fixed-state 61-row comparison the largest time-varying nuisance change is the receiver smooth term, 4.72 / 3.34 Hz RMS after centering, and both complete gates remain inside their limits. [Gate implementation](../../../src/leo/analysis/localization_v3/conservative_recovery.py) · [Original diagnostics](../../../src/leo/analysis/research/polynomial_satellite_diagnostics.py)

The excluded observation is the tail at 49.4855251 s in the original detector clock, with native margin 0.124905, third weakest of the 62. Its conditional residual is 382.90 / 383.68 Hz. It has the largest influence on the step across all one-observation deletions in both arms. Three of the 62 single deletions pass the conditional check in each arm. Only the chronological tail passes among endpoints. A bounded causal test can attempt the two contiguous one-point endpoint trims after a step-only failure, require that the same unique trim clears both original full local gates, then charge one paired fit and recheck every retained family. If the recheck fails, keep the existing repair. This diagnosis did not run or time that fit.

## The 62735 curve depends on the surrounding calibration

Both paths used the same 48 observations and native alias +1. The actual cumulative early fixed-zero second gate has slope z **3.590**, over the 3 cutoff, with a matching phase-profile slope and all other verified scalar thresholds satisfied. The cumulative route has no fitted-c second gate at that stage. The fitted-c cells below use the actual later intact cumulative paired reference as a donor.

| Curved calibration context | Position and phase-reference source | Slope z, fixed zero | Slope z, fitted c |
| --- | --- | ---: | ---: |
| Named signed, 4,150 observations | Named signed pair | 2.077 | 1.340 |
| Named signed, 4,150 observations | Cumulative intact paired fit | 2.137 | 1.393 |
| Cumulative second gate, 4,515 observations | Named signed pair | 3.527 | 2.433 |
| Cumulative second gate, 4,515 observations | Cumulative intact paired fit | 3.584 | 2.478 |

At each fixed position the original likelihood re-solves the nuisance state. Each recipient keeps its physical support and prior means. Exact phase coordinates transfer by NORAD, with 33–34 coordinates available in these cells. Hyperparameters match across the real contexts, including Student ν = 3 and phase-width multiplier 0.545692. Signed per-family means, unmatched phase coordinates and orbital-mode eligibility remain attached to their original contexts. The measurement cannot allocate the context effect uniquely among every missing observation, prior mean and orbital mode. In the fixed-state decomposition, transferring just the named receiver hardware term shifts the actual early slope from 3.590 to 2.979. Transferring just its orbit term gives 3.018, and just its receiver smooth term gives 3.414. These are conditional residual contrasts before a common refit or full paired admission.

The weight exchange covers all 4,150 named points and 85 active fragments against 4,515 points and 98 fragments in the early cumulative calibration. It can copy 4,102 common points and 84 fragments across the named and intact cumulative 58377 contexts. Changing the shared weights and point noise produced identical gate and state readouts in every cell. Recipient-only weights are held at their own values.

The independently signed salvage supplied these 48 points, together with 364 other reintroduced points. The second curved gate rejected every addition. In the retained trace, 62735 is the only independently proposed fragment that keeps its prior NORAD and trips just the conditional slope limit with the other recorded thresholds satisfied. The original profile readout separately confirms its only failing shape statistic is slope. A bounded causal test can take the original surviving calibration and reintroduce this class of independently proposed fragments one at a time, using the original alias and phase evidence. Rerun the original paired gate before enabling ordinary predictive nomination. This avoids paying to fit all unqualified additions together. The original 4,103 cumulative survivors plus these 48 observations equal the 4,150 named curved rows plus the one trailing 58377 observation on this recording. That equality uses named support for verification after capture. It does not supply any rows to the causal intervention.

The two linked predictive 62735 fragments are 17 and 15 observations, from different receivers. Both named predictive arms keep them with alias 0. Their native predictive RMS ranges from 75.5 to 132.3 Hz and their step z from 1.60 to 1.80. The captured cumulative association never offered that NORAD to predictive nomination after the curved gate removed it. Restoring eligibility gives the original solver a chance to nominate the 32 observations. The diagnosis does not show that it would adopt them. The separate 32-point RX1 CH5 T008 curve had nearly 30 kHz conditional mean and failed the original bias and shape checks. It was absent from named selected support.

## Charged work and reproducibility

| Saved diagnostic stage | CPU seconds |
| --- | ---: |
| Named entry to genuine pre-nomination incumbent | 29.078 |
| Named owner and objective verification with grid disabled | 0.388 |
| Cumulative entry to intact pair, before repair | 14.525 |
| Fixed-position, term and exact-mask comparisons | 1.281 |
| Whole child through exit | 46.128 |

Elapsed through exit was 46.146 s with zero kernel input blocks and major faults. The named cutoff reproduced rank 1, exact positions and RF metrics, all 4,821 ordered owners per arm and zero objective replay difference. Its archived full path adopted no cavity change. The cumulative cutoff reproduced the archived target rows of the first and second curved gates, the pre-repair decision and predictive-family eligibility. Both use the original signed 20 ms packet, explicit offer and causal tmpfs archive. There was no raw acquisition, publication, grid rendering or survey input. The two earlier launcher attempts exited before any stage capture in 0.082 and 0.093 CPU s from installed-import mismatches. The source corrected admission and the single paid diagnostic exited successfully.

Run `fragment_gate_cross_0402.py launch NEW_TMPFS_ROOT` with the installed named interpreter under the Gauss CPU 2 lock, low process and I/O priority and one numerical thread. Run its post-exit `seal NEW_TMPFS_ROOT RECEIPT` with the same research, checkout and release import paths. The full receipt retains each local threshold and reconstructed cell. [Driver](fragment_gate_cross_0402.py) · [Component tests](../../../tests/pipeline_eval/test_fragment_gate_cross.py)
