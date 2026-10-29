# Receiver-feedback ablation on five rejected curves

The [previous receiver-ramp experiment](../2026_10_29_independent_receiver_ramps/README.md) excluded the target satellite from calibration, but Gaussian predictive conditioning still updated receiver uncertainty using target training points. This experiment blocks that update at each fixed satellite phase. It replays all five cases, three models, three randomized block partitions and both c arms. No GPS or future TLE enters fitting or selection. Original identities and aliases remain frozen; this is not renewed identity validation.

## What is frozen

Write the target prediction covariance as `B + F`, where `B` contains independent satellite orbital modes, a 300 Hz track-bias prior and observation noise, and `F` is the receiver posterior covariance projected onto target timestamps. Receiver coefficients and their marginal covariance come entirely from other satellite families. With target training indices t and held indices h, `K = B_ht inv(B_tt)`:

```
held mean = m_h + K (y_t - m_t)
held covariance = B_hh - K B_th
                + F_hh - K F_th - F_ht K.T + K F_tt K.T
```

This integrates the unchanged receiver distribution after conditioning satellite nuisance terms separately for each receiver realization. Target observations cannot reduce the receiver marginal variance. If there is no satellite nuisance and only one phase, target training changes neither the held mean nor its receiver variance; an explicit regression test checks this.

Phase weights still use training likelihood marginalized over receiver uncertainty. The phase distribution is then factorized from the original receiver marginal: this is a **modular approximation**, not an exact joint Bayesian posterior or proof of hardware causation. Target training may identify satellite phase, orbital modes and bias. We also compute a stronger `no_target_training` diagnostic that uses the causal phase prior without any target training frequencies. Its uncertainty is intentionally broad; it is not an identity acceptance rule.

## Results

| scan | model | score_improved | rms_improved | worst_score_delta | worst_rms_delta_hz | predictive_screen_pass |
| --- | --- | --- | --- | --- | --- | --- |
| AUTO-c0dd2487 | receiver_hz | 6 | 6 | -0.540 | -12.470 | True |
| AUTO-c0dd2487 | receiver_fractional | 6 | 6 | -0.543 | -12.418 | True |
| AUTO-7ec14096 | receiver_hz | 6 | 6 | -0.071 | -9.524 | False |
| AUTO-7ec14096 | receiver_fractional | 6 | 6 | -0.048 | -8.822 | False |
| AUTO-453faf4c | receiver_hz | 4 | 4 | 0.869 | 17.101 | False |
| AUTO-453faf4c | receiver_fractional | 4 | 4 | 0.909 | 18.116 | False |
| AUTO-8d229584 | receiver_hz | 6 | 4 | -0.112 | 18.271 | False |
| AUTO-8d229584 | receiver_fractional | 6 | 4 | -0.176 | 14.685 | False |
| AUTO-d9185bf9 | receiver_hz | 6 | 6 | -1.417 | -16.811 | True |
| AUTO-d9185bf9 | receiver_fractional | 6 | 6 | -1.632 | -20.018 | True |

Each count is out of six matched comparisons (three partitions × two c arms). Lower density scores and RMS are better. The unchanged diagnostic screen additionally requires existing-family held scores not to worsen, phase convergence ≤0.01 s, visibility and boundary mass ≤0.05. The screen is not a calibrated population false-association bound. A failure identifies a weakness to investigate; it does not prove the curve is not a satellite.

[Every comparison](scores.csv), [all diagnostic screens](qualification.csv), [execution receipts](execution.csv), and [all figures](gallery.md) include unfavorable results. Original objective and ordinary predictive-score replays differ by at most 0 and 0, respectively. No position fits are rerun: previously reported position gains remain conditional on their earlier full-fit checks and are not new results of this validation.

## What this changes about the earlier promising results

The extra checks narrow the conclusion. AUTO-c0dd2487 improves target prediction with receiver feedback blocked, under both correction models, and its earlier full fits pass. However, [renewed satellite competition](satellite_competition.md) leaves its identity below the existing conditional-score margin threshold. The [joint-evidence diagnostic](joint_evidence.md) investigates why an alternative with very poor training evidence remains competitive on one held partition. It proposes a scoring hypothesis; it does not change acceptance.

AUTO-8d229584 retains strong support for satellite 100017 under renewed competition, but its corrected frozen-receiver RMS worsens in one of the three partitions (both c arms). Its earlier position improvement therefore remains provisional. AUTO-d9185bf9 passes the receiver-transfer screen but still has the previously documented orbital-support and old-track full-fit failures. AUTO-7ec14096 remains pinned to the phase boundary despite lower RMS; AUTO-453faf4c worsens on one held partition. The additive-Hz and RF-proportional results remain similar, so these cases do not distinguish the physical receiver mechanism.

**Neither of the two earlier full-fit success cases is ready for promotion after all of these new checks.** This is progress in locating the bottleneck, not a new dataset-wide position gain. The graph assessment ledger remains 744/1,630; this iteration investigates existing cases rather than adding annotations.

## Reproduction and scope

`probe_frozen_receiver_transfer.py --previous .../independent-receiver-ramps-v1 --output .../frozen-receiver-transfer-v1` runs five bounded workers, with 600 seconds per case. The original training protocol, causal catalogue, 25×25 km regional-center start, 5 phase-refresh rounds ×48 iterations, 150 Hz training noise, 0.025 s prediction phase grid, 12 s randomized blocks and 2 s guards are unchanged. Calibration checkpoints save the actual final phase reference and keep mask for subsequent exact replay. Receiver ramp priors remain exploratory: 50 Hz per 10 s continuous increment, additive-Hz or RF-proportional.

The tests cover analytical latent integration, the zero-receiver-uncertainty limit, target feedback prevention, absence of held-data leakage, covariance validity and unchanged existing predictor behavior. Evidence and [source hashes](sources.json) accompany this report. New-cohort tests and competing satellite identities are required before production promotion. No production behavior or ALGO version changes here.
