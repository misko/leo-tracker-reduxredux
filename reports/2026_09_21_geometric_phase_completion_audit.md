# Geometric phase recovery: remaining evidence

This audit checks the original objective against the saved recordings and current research results. Better agreement between estimators is progress, but does not establish separation of satellite geometric phase from the receiving paths. The objective is **not complete**.

| Requirement | Current evidence | Disposition |
|---|---|---|
| Use existing recorded IQ | Recent eight-hour inventory and selected replay digests; no new RF | Established for the analyzed recordings |
| Track overlap on both receivers | Recent exact shared-visit inventory; earlier 28d common-support matched-pilot measurements | Available on selected support; source identity remains conditional on RF association |
| Resolve frequency/timing ambiguities | Broadband frequency authority, common-time comparisons, device counters, wrong-alias controls, opt-in shared residual | Important errors corrected; pilot coherence alone cannot validate frequency branch |
| Quantify phase uncertainty | Conditional bootstrap/fit errors and symbol/time-subset checks | Partial: the recent validation still has a 54.84-degree half-window discrepancy; these are not total calibrated errors |
| Separate geometric phase from receiver/channel terms | Simultaneous DD cancels the common receiver term on qualified support | Not established for source-dependent transfer, path delay, estimator bias, or individual-source absolute phase |
| Check geometric interpretation | LT3D-001A mesh, orbit sensitivity distributions, orientation-independent circular-orbit curvature bound | Mechanical geometry verified; installed RF baseline and source directions are not established by that mesh |
| Recover true satellite geometric phase | No validated decomposition or independently anchored geometric curve | Unproven |

## Recorded geometry and calibration authority

The raw manifest for `scan-hop-6adcb067e2dbce43` was inspected again, read-only. Its geometry binding is `sha256:55e5a117d885e8ac158a0a41895b66cb5be881d66630d2765fccf5711a21643f`. Both slots have null `rf_phase_center_position_m` and `rf_boresight_unit`; both receiver-to-slot assignments have `mapping_status: provisional`. The mapping evidence explicitly says the physical left/right cable trace has not been recorded. No differential phase/delay calibration is bound in this manifest.

The repository also contains items called “calibration,” but the inspected examples do not supply that missing evidence:

- `config/analysis/fixed500-calibration-protocol-v1.json` is a polynomial-injection analysis/uncertainty experiment.
- `ReceiverFrequencyCalibrationV1` in `src/leo/contracts/calibration.py` stores an empirical frequency center and frequency uncertainty for one physical path, not electrical phase/delay response.
- `docs/qualification/frequency-calibration.md` explicitly describes acquisition/search-center calibration that includes satellite Doppler, rather than intrinsic LNB error.

This is an audit of the bound inputs and inspected repository evidence, not a claim that no relevant reference recording exists anywhere. The user has been asked for the location of any existing shared-reference or differential phase/delay recording.

## Why another uncalibrated phase curve does not close the gap

For a source s, write the measured receiver difference as

`D_s(t) = G_s(t) + C(t) + H_s(t)`.

G is geometric phase, C is common receiver/oscillator phase, and H contains source/frequency-dependent receiver/channel terms and remaining measurement bias. Simultaneous DD removes C, leaving `G_B-G_A + H_B-H_A`. An unknown constant differential H still shifts the absolute DD. If H is independently justified as time-constant, temporal DD removes that constant; absolute phase calibration is therefore **not required for every useful geometric change measurement**. The earlier stable-LNB assessment remains applicable.

Here, stable warmed-up LNB behavior is the user's modeling assumption, not a measured bound on every term in H. Corrected estimator diagnostics still disagree in some dwells. The earlier 28d DD fluctuations also require several-degree corrections to fit the illustrated orbital-curvature bound. Simply labelling these residual terms zero would assume the requested separation instead of demonstrating it.

An independently known phase/delay reference on the relevant paths could constrain receiver terms. Independently established source directions together with installed RF geometry and a validated stable response model could provide another route. A common tone injected only after the LNBs would calibrate only the downstream portion; it would not by itself characterize the LNBs or their direction-dependent antenna response. Any supplied reference must therefore be checked for path coverage, capture epoch, frequency range, uncertainty, and its relation to the analyzed scans.

## Existing results to retain

- [Recent long trajectories and phase results](2026_09_21_recent8h_long_track_phase.md).
- [20-visit shared-residual validation](2026_09_21_shared_residual_phase20_validation.md): median disagreement on the 18 validation visits improves from 11.91 to 3.17 degrees; the largest remains 54.84 degrees.
- [Simultaneous matched-pilot DD](2026_09_21_scan_hop_28d_matched_pilot_dd_cohort.md): common receiver cancellation with conditional uncertainty, but unresolved visit-to-visit variation.
- [Orbital-curvature check](2026_09_21_geometric_phase_curvature_check.md): at least 5.32 degrees of uniform point-error allowance is required by one triple under the stated scenario.

Further refinement of these same unanchored observations cannot alone certify an absolute geometric phase. The next discriminating input is an applicable independent reference or physical-response constraint. No new collection is started by this audit.
