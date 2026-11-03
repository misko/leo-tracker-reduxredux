# DS10 Doppler sensitivity to position and timing

The failed DS10 N24 transfer fit retains measurable local position sensitivity, but free recording timing removes substantial information in one horizontal direction. In this conditional diagnostic, a one-kilometre displacement corresponds to about 15–21 Hz RMS after timing adjustment. This supports prioritizing independent timing evidence; it does not identify timing as the cause of the actual position error.

| Conditional frequency change per kilometre | Timing fixed | One timing adjustment per scan |
|---|---:|---:|
| East displacement | 24.295 Hz RMS | 14.825 Hz RMS |
| North displacement | 21.633 Hz RMS | 20.915 Hz RMS |

After timing projection, the weakest and strongest horizontal directions have sensitivities of **14.685 and 21.013 Hz RMS/km**. The generalized information-retention eigenvalues are **0.37024 and 0.93471**: free timing removes about 63.0% of information in the most affected direction and 6.5% in the other. These are conditional weighted design metrics, not location-error reductions or calibrated confidence bounds.

For a positive one-kilometre east perturbation, the best linear timing compensation ranges from **+35.7 to +135.2 ms** across the 24 scans, with median **+110.7 ms**. For north it ranges from −58.4 to +46.3 ms, with median absolute magnitude 23.6 ms. Timing does not absorb the entire position signal. This calculation also does not justify applying those offsets to real data.

## Method and limits

The [protocol](PROTOCOL.md) predates execution. All 1,443 tracks from the frozen DS10 N24 height-zero fit remain included. Each uses its original training-selected top candidate, weighted by conditional candidate probability times signal responsibility. The calculation differentiates the existing frequency predictor, removes a separate training mean for each track to eliminate constant frequency offset, then projects out one shared timing derivative per scan. No reference coordinate is used to select a perturbation or parameter.

The reported Hz/km numbers are local derivatives scaled to a one-kilometre displacement, not a nonlinear injection. Weighting depends on the fitted candidate model. Candidate uncertainty derivatives, cross-track correlations and systematic model error are omitted. The underlying complete-data approximation can overstate usable information. It does not certify the candidate identities, the DS10 physical installation or true accuracy. The earlier [DS7–9 injection experiment](../2026_09_29_position_injection/README.md) supplies a separate model-conditioned nonlinear test.

## Verification and consequence

The original training score replays within 1e-7. Candidate visibility remains unchanged over derivative perturbations. Halving the 1-metre position and 10-microsecond timing steps changes the fixed and profiled matrices by only 1.30e-9 and 1.24e-9 relative norm, respectively. Two component tests pass for exact collinear timing removal and zero-timing information preservation. All 24 scans complete in 7.81 seconds under the 120-second cap.

[results.json](results.json) preserves per-scan RMS values, weights, track and observation counts, timing compensation and source bindings. [run.py](run.py) uses existing derived banks and does not refit a position.

The useful next timing experiment is to quantify performance under independently defensible timing constraints. A tight prior selected because it improves distance to the roof reference would not provide that evidence. The [historical timing audit](../2026_09_29_timing_authority/README.md) and [physical evidence check](../2026_09_30_physical_constraint_audit/README.md) still lack a capture-level historical UTC bound. Separately, the size of this Doppler signal reinforces why unconstrained residual-slope corrections can erase position information rather than improve location.

No RF collection, raw IQ processing, production change or remote publication occurred. No new sub-km accuracy result is claimed.
