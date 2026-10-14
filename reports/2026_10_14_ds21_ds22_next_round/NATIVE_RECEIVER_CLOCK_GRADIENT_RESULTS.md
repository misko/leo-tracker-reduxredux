# Strict gradient finishing converges within the original numerical budget

The C001 native-clock warm fit now passes the unchanged independent stationarity audit. One Newton step in the tangent of the active affine timing constraint reduced KKT from 0.002061475 to 7.456362e-8. The complete native fitting path used 477 objective evaluations and 16.873384 seconds, within its declared 600-evaluation/20-second cap. The original SLSQP fit is retained in the receipt, and no tolerance was loosened.

| Measurement | Original C repeat | Native clock with gradient finish |
|---|---:|---:|
| Objective | 41863.551059 | 41418.038342 |
| Training NLL | 41529.962579 | 41017.333838 |
| Independently audited stationarity | 0.000157949 | 0.000000074564 |
| Configured-reference distance km | 21.266493 | 19.428852 |

The position comparison was computed after both outcomes were sealed and independently accepted. DS22 reference remains configured-unconfirmed. The prior cold-start native-clock result was 29.257438 km; this new warm experiment adds work and is not an equal end-to-end search-cost comparison. It improves initialization and numerical convergence but still misses the localization target badly. No full-cohort model promotion is justified.

Both calls start from the original training-selected C winner with the same explicit sub-1e-8 timing-margin projection and original winning 25 km disk. The augmented arm adds zero-initialized receiver clocks. It runs the original fitter and spends only its remaining time/evaluations on the finishing step. All numerical derivatives count toward the native path limit. The original model is repeated under its existing 20-second/600-iteration budget; its independent audit passes.

The finisher is restricted to near-stationary endpoints. It preserves active affine constraints, refuses active curved geographic constraints, requires positive-definite tangent curvature, limits step size, checks feasibility, requires the full KKT residual to halve, and accepts only the original 0.001 full stationarity threshold. Very small score changes have a bounded floating-point safeguard; the actual accepted step decreased objective without needing that allowance. Failed finishes retain the original unaccepted result.

Actual finishing work: 146 evaluations, 5.093751 seconds, 72-dimensional tangent, minimum tangent eigenvalue 0.919924, tangent/normal residual 1.87e-16, scaled step norm 9.31e-6. Its full Newton predicted decrease was 5.97e-10 (about 82 objective ULPs), larger than the earlier individual-coordinate predictions. Thus the scalar probes did not describe the total available improvement; this experiment demonstrates a successful gradient-based correction, not proof that scalar rounding alone caused SLSQP's stop.

Source `be2886180`; eleven tests pass, including a real native objective/SLSQP integration, large objective offset, active-bound preservation, wrong-multiplier rejection, saddle rejection, infeasible probes and hard evaluation counts. Ruff passes. The complete two-call control, including preparation and independent audits, took 51.029038 seconds. No reference or held data was used during fitting.

Receipts: `local/ds22-native-clock-gradient-control-v1` and post-seal `local/ds22-native-clock-gradient-comparison-v1/report.json`. Terminal SHA256 `cfea8304de740835e16b75d51fa3b0a189db8353ce8409a3b342c86abb857ee9`; seal SHA256 `bb1a97be2e2ad4a84bf51bfa4fff2c5b2778e65f867e195626218d6e16f83be1`.
