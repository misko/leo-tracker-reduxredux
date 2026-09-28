# Independent review of the receiver-drift recovery prerequisite

## Decision

The Wave 3 recovery is admissible as a **software and local nonlinear-recovery diagnostic**. It is not evidence that DS7 contains a receiver-clock drift, that the two fitted slopes represent physical clocks, or that adding them improves position inference. The original real-clock gate therefore remains closed.

A separately named, predeclared **unregularized shadow diagnostic** on real observations would be scientifically admissible without a calibrated prior only if its output is quarantined from geographic scoring and model selection. It must report the training profile, frozen held-observation prediction, boundary and constraint-removal behavior, and candidate-responsibility changes. It cannot be promoted to the baseline or interpreted as receiver calibration until the independent evidence listed below exists.

The most defensible next model direction is a per-capture linear **receiver-path frequency nuisance** in native Hz/s, mapped into the exported frequency convention by `11.2 GHz / actual RF`. Calling it a clock state is premature. Hardware evidence must first decide whether the two receive paths have independent slopes or one shared slope. No cross-capture sharing is admissible yet.

## What the recovery establishes

The experiment uses the sealed baseline estimate only as a non-reference donor center. It selects one training-MAP candidate per track, profiles that candidate's stationary offset, generates noiseless observations from the same timing-bank interpolation and Doppler implementation used by the fitter, and then fits the full candidate mixture from three fixed starts. All three predeclared injections complete within their case limits and recover position within 3.12 m, recording time within 0.000209 s, and slopes within 0.00758 Hz/s. None of the reported solutions is at its numerical bounds.

This is useful evidence that the optimizer can recover a small linear perturbation near this donor solution and that the implemented slope gradient has the expected sign and scale. The component finite-difference test supports the one-track profiled slope derivative. The later conditional Jacobian independently reports rank 61/61, scaled condition number about 55.35, and residualized receiver-column norms 0.594 and 0.941 under fixed responsibilities and positive Student-t weights. Together these clear a local computational prerequisite.

They do not test noise, orbit error, propagation interpolation error, transmitter drift, extractor bias, candidate-family misspecification, or a candidate switch induced by real residuals. Synthetic truth is a hard component from the same bank and the fit uses the same likelihood and interpolation. The zero-slope case is also synthetic; it is not the original gate's required zero-correction replay of real baseline predictions and residuals.

## Model and unit audit

`drift_column` implements

```text
exported frequency perturbation = native_slope_hz_s
                               * (11.2e9 / track.rf_hz)
                               * (track_time_s - track_mean_time_s)
```

That is internally consistent with the Wave 2 correction for an additive native baseband frequency slope when measurements are represented at the fixed 11.2 GHz model convention. It differs from the literal Wave 1 frozen configuration, which said that absolute baseband drift had no frequency scaling. Wave 3 therefore tests the corrected physical-baseband convention, not the original text. Any future specification should explicitly supersede that field.

This term is not a complete sample-clock model. A fractional oscillator error can also perturb sampling time, acquisition timing, and the effective tuned frequency. An LNB or transmitter frequency trend can appear in the same measured CFO. The current data model only introduces an additive linear frequency nuisance. Its fitted coefficient should retain that limited name unless an external calibration identifies the mechanism.

Centering uses the mean of all observations in each track, while fitting uses only the training mask. With freely profiled per-track constants, changing the center adds a track constant and leaves the slope likelihood invariant. The baseline gives offsets a weak Gaussian penalty, so the invariance is not mathematically exact. A real diagnostic should bind one common capture-time origin for physical interpretation and may separately center columns over training rows for numerical conditioning; it should verify that this choice does not materially alter the fit.

## Concrete implementation findings

The reported `projected_rank` is not the full nuisance-projected information of the fitted mixture. It chooses one MAP candidate per track, uses unweighted finite-difference columns, and removes a simple per-track mean. It omits Student-t weights, candidate responsibility derivatives, offset-prior curvature, and component switching. Its rank 5/5 and condition 38.56 are a selected-component structural screen. The Wave 2 weighted fixed-responsibility calculation is the closer local screen, though that also is not global mixture information.

Two qualification checks declared by the original gate are not enforced by `run_case`:

- `boundary_hit` is computed but is not included in `qualified`.
- The result status checks rank but does not apply the declared condition-number ceiling.

Neither defect changes these recorded cases because every reported `boundary_hit` is false and the reported condition number is below 1,000. They must be fixed before reusing this analyzer as an admission gate. The tests exercise a single-profile slope derivative but not the complete five-parameter mixture gradient; a full-objective finite-difference test is still required. Constraint removal, standard errors, independently bounded endpoint recovery, real zero replay, and frozen held prediction are not implemented in this experiment.

The predeclared recovery tolerances and the +/-2 Hz/s optimizer bounds are computational choices. Recovery of injections at 0 and +/-1 Hz/s does not turn either number into a physical bound.

## Independent evidence still required for model admission

The following evidence must be obtained independently of DS7 positions, reference scores, and residual-based tuning:

1. **Clock topology and identity.** Bind radio serial, physical receive path, clock source, firmware/configuration, capture interval, RF/channel, sample rate, and hardware epoch. Establish whether RX0 and RX1 share the oscillator and LNB path. Use one shared slope unless evidence supports independent path slopes.
2. **A valid drift bound.** Measure the complete receive chain against an external frequency/time reference over intervals at least as long as a fitted capture, or derive a conservative rate bound from applicable hardware specifications plus temperature/aging limits. A static ppm accuracy specification alone is not a drift-rate bound. The evidence must state the transfer law into native Hz/s and then into exported frequency units.
3. **Mechanism discrimination.** Show that the measured effect is compatible with an additive receiver-path frequency slope rather than sample-time warp, LNB drift, emitter drift, or estimator bias. If this cannot be shown, retain the parameter as a nuisance and do not share it across emitters or captures.
4. **Real-data identifiability.** On the sealed candidate mixture, report a full-objective derivative check, local/profile curvature, responsibility changes, and sensitivity to orbit/candidate alternatives. Apply the original rank, projected-norm, condition-number, boundary, and constraint-removal rules.
5. **Prediction rather than refit.** Fit only frozen training observations and evaluate the same parameters on predeclared held observations without fitting held frequencies. Any improvement claim must use a common held objective and include the zero-slope replay. Residual reduction on training data is insufficient.

## Recommended next admission step

Hold the calibrated clock variant and all geographic claims. If the coordinator wants information before external calibration is available, admit one frozen, single-capture shadow diagnostic with both of these nested forms: one slope shared by both receiver paths, and two slopes only if the hardware identity audit permits them. Use a common capture-time origin, the corrected native-to-exported scaling, no slope prior, and bounds wide enough that the solution and its uncertainty are demonstrably interior. Freeze the candidate bank, masks, starts, objective, held rows, and rejection rules before execution.

The diagnostic passes only as evidence for continued study if the full gradient check passes, zero replay is exact, the unregularized profile is interior and locally identified, widening/removing computational bounds does not move the estimate materially, and frozen held likelihood improves without a large candidate-responsibility collapse. Regardless of that result, model adoption remains blocked until independent topology and drift-bound evidence exists. If topology shows a shared oscillator, the two-free-slope model should be rejected in favor of the shared-slope form rather than treated as a more flexible clock correction.

## Evidence boundary

Reviewed artifacts and SHA-256 digests:

- Wave 3 specification: `c7c9132a125238d219ddd581addb651e644571b17aaf25b14fd50d7b2bc5fbe3`
- Wave 3 result: `114a84eadb45085f786922e9efc2906c2527ac7ee51078a79a27825d8eaab6a5`
- Wave 3 analyzer: `6189882c086911468c313130a7be99b5e3a1721d0b63d814370cc8b8d0d5643d`
- Wave 3 component tests: `ca43dd2d82d4866e4a135ca900653185a49466e5136b6404548a4d200a09265d`
- Original frozen gate: `bac4c268872e733e2dc22bfcd7606685f0236d4a37d9a84533d297106a65e2fc`
- Wave 2 conditional Jacobian receipt: `60acedbae66555a28a3e8793b300380963f64155408bda717a9c72609382db58`

No DS7 score, reference position, pose, IQ, or full manifest was read. No real-data clock fit was run, and no sealed artifact was modified.
