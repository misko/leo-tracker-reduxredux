# DS6 Doppler and range-rate consistency audit

Exact state-velocity Doppler agrees with central differences of exactly propagated satellite ranges to within 0.45 Hz on the four pre-existing development scans. After subtracting the training-mean difference for each track, the largest discrepancy is below 0.20 Hz. This does not identify a large velocity/frame inconsistency worth changing in the fitted model.

| MS/s | Maximum raw difference (Hz) | Maximum training-centered difference (Hz) | Maximum step-halving difference (Hz) |
|---|---:|---:|---:|
| 10 | 0.4141 | 0.1089 | 0.0718 |
| 2.5 | 0.4157 | 0.1165 | 0.0739 |
| 5 | 0.4487 | 0.1171 | 0.0912 |
| 7.5 | 0.4304 | 0.1998 | 0.0919 |

Each included track selects its candidate by the original stationary training likelihood and visibility at the corrected independent fitted position and timing. Exact propagation supplies positions at receive-plus-tau epochs and at +/-0.1 and +/-0.05 seconds. Range derivatives use the same stationary Earth-fixed receiver and the same 11.2 GHz normalized reference as the velocity-based model. Candidate row IDs must match across propagation calls. No geographic reference is loaded, and no position is refitted.

The differences between the two finite-difference steps are non-negligible relative to the sub-hertz discrepancy. Do not interpret the smaller-step result as exact, claim an asymptotic convergence rate, or treat the full discrepancy as a physical correction. The experiment checks internal numerical consistency only; it cannot establish TLE accuracy, transmitting satellite identity, absolute clock accuracy, or a bound on resulting position error. The training-mean subtraction is a shape diagnostic, not a replacement for the robust fitted offset.

Source inspection also confirms that trajectory construction scales measured CFO once by canonical_rf_hz / actual_rf_hz, while prediction uses the same 11.2 GHz canonical reference. No second frequency scaling is justified by this inspection. It does not independently calibrate the hardware RF frequency.

Two tests verify the radial-velocity sign and frequency scale, complete track coverage, frozen source and input hashes, and aggregate consistency. No scientific fixture or production implementation was changed. The verified positioning results remain 754.938 m for the combined estimate and 6/43 individual scans below 1 km.
