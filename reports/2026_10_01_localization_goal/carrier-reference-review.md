# Nominal carrier-reference sensitivity

The pilot-center/tuner-center distinction is present in only part of the 12-scan development panel and has a small local position effect. It is not supported as the main explanation for kilometer-scale errors.

Six scans have maximum nominal pilot-to-recorded-tuner differences of 2–4 Hz, with predicted local displacements below 0.001 m. Six have 312,500 Hz differences, with predicted displacements of 21.48–45.23 m. The largest change to a retained contrast prediction is 3.019 Hz. These are first-order IRLS sensitivities, not nonlinear fits or measured geographic improvements.

![Carrier-reference sensitivity](carrier-reference-v1.png)

## Trace and calculation

The prior DS7 frequency-reference audit already established that persisted normalized CFO uses the recorded tuner RF as denominator, not an independently measured transmitter carrier. Its example used 10 MHz capture bandwidth and a 312.5 kHz nominal pilot-to-tuner difference. That difference must not be copied indiscriminately across recordings. The current panel contains both near-pilot tuning and offset tuning.

The frozen observation loader copies `measured_hz` unchanged and retains each track's `rf_hz`. Acquisition and selected-track prediction use the canonical 11.2 GHz Doppler coefficient; receiver drift is separately scaled by `11.2 GHz / track.rf_hz`. With the already normalized measurements unchanged, a nominal carrier replacement changes only the orbital prediction by the multiplier `f_pilot / f_tuner`. The per-track constant frequency offset has already been removed by contrasts.

For each original sealed state, infer the nearest nominal lower/upper pilot from recorded channel and RF. Require it to be within 1 MHz; retain the inferred-edge qualification because the exported metadata omits explicit edge. Use nominal lower/upper channel-1 centers 10,709,687,500 and 10,940,312,500 Hz, with 250 MHz channel spacing. These constants were read from the pinned deployment contract:

`/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/lib/python3.14/site-packages/leo/contracts/starlink_frequency.py`

Its SHA256 is `835a26aff7a7ccc968470161146d940dc477147cbe5e3697eb85e092495aa885`, matching the prior audit's contract version. The contract was inspected read-only, not imported as a runtime dependency.

Let `epsilon = (f_pilot-f_tuner)/f_tuner`, and let `d` be the selected prediction after subtracting its receiver-drift term. The perturbation is `delta_mu = epsilon*d`. Assemble original fixed Student IRLS weights and full position/nuisance Jacobians. With Gaussian prior precision `P`, solve

`H delta_x = -sum Jᵀ W delta_mu`, where `H = P + sum Jᵀ W J`.

Report the norm of the east/north component in meters. Keep fixed height, identity assignments, sample membership, weights, Jacobians and original nuisance priors. This is the displacement predicted by a quadratic surrogate; it does not certify movement of the nonlinear optimum.

## Verification and decision

All 12 parent seals, frozen sources, input digests, height bindings and observation lists were checked. Track IDs join uniquely to the exported RF/channel metadata used here, and RF values match the prepared tracks. The linear systems satisfy their normal equations; reversing the perturbation reverses the predicted step. The audit took 25.34 s total without fitting, reference-coordinate reads, or new RF collection. Authoritative evidence is `carrier-reference-v1.json`, its SHA seal and recorded source/input digests. The figure was visually inspected.

Do not promote a correction on this diagnostic alone or fit arbitrary carrier scales to exposed GPS errors. Unknown physical LNB, transmitter, receiver-clock and within-pilot-band frequency errors are not bounded by the nominal tuner/pilot comparison. A discrete identity switch is also outside this local calculation.

The original 64-scan benchmark remains unchanged: 2,059.90 m median error, 5,850.75 m p90, 64/64 acceptance. No uncertainty-calibration or held-out improvement is claimed.

Next, review existing timing audits and trace the observation timestamp from capture/window metadata to exported track time. Distinguish a deterministic window-origin or midpoint convention from a fitted clock correction. Such a source audit can establish whether a correction is physically supported before adding another nuisance parameter or performing another geographic fit.
