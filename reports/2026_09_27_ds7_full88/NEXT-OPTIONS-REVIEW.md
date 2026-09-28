# Next options if the frozen full-88 joint fit misses 1 km

This review is read-only and does not depend on the live full-88 score. It does not authorize a retry, a parameter change, a dropped capture, or selection by geographic error. The next useful step is diagnosis on frozen training and held observations; model changes require their own predeclared gates.

## 1. Audit where the joint constraint loses predictive support

This is the strongest next action once a full-88 response is sealed: the required observations, candidate banks, masks, sealed single fits, and group fits are already on disk, while the full-88 fit is still running. Repeat the reference-free decomposition used by the [first-eight residual audit](../2026_09_27_ds7_wave3/residual/README-v2.md): compare the frozen joint prediction with independent and group predictions on identical memberships, report training likelihood and fixed-parameter held predictive likelihood separately, and stratify residuals by capture, receiver, channel, RF lane, track, candidate responsibility, and time. The existing audit found that the first-eight joint fit lost 713.85 training nats and 432.55 held nats versus independent fits, with seven of eight captures losing held density; that is direct evidence that a shared-position fit can expose structured mismatch.

Evidence needed for a next model: a predeclared residual pattern that repeats across disjoint chronological groups and held observations, survives candidate alternatives, and improves a common held objective without fitting held frequencies. Existing frozen products can satisfy this gate. Geographic error must remain out of feature selection and threshold choice.

## 2. Treat association and search as diagnostics, not a score-driven rescue

The [association gate](../2026_09_27_ds7_wave1/association/REPORT.md) verifies complete masks, timing grids, catalogue normalization, causal elements, and shortlist structure. The first bank retains at least 0.9363 top-eight posterior mass per scored cell, but this is conditional on an incomplete candidate bank and does not establish physical identity. The [frozen association specification](../2026_09_27_ds7_wave1/association/SPEC.md) defines matched local/multibasin, trajectory-reversal null, explicit per-track null, permutation invariance, and synthetic-injection controls. The scored first-session multibasin result was unqualified, while the matched local result qualified; therefore broader search has not earned promotion ([local receipt](../2026_09_27_ds7_wave1/coordinator/association-local-score-v1/REPORT.md), [multibasin receipt](../2026_09_27_ds7_wave1/coordinator/association-multibasin-score-v2/REPORT.md)).

Existing on-disk banks can support reference-free objective/start accounting, deterministic replay, null responsibility, trajectory-reversal controls, candidate-responsibility stability, and held predictive comparison across all captures. A scientifically viable association change needs synthetic discrimination against the mismatched trajectory, exact compute parity, an interior solution, and improved frozen held likelihood across predeclared groups. Candidate-label permutation is only an invariance test. No candidate cap, basin, null weight, or membership may be selected from geographic scores.

True blocker for a physical association claim: there are no independent satellite-identity labels. Candidate concentration or repeated catalogue leaders cannot substitute for them.

## 3. Keep receiver drift as an unscored shadow diagnostic

The [clock review](../2026_09_27_ds7_wave4/clock-review/REVIEW.md) admits the implemented receiver-path slope only as a software and local nonlinear-recovery diagnostic. Synthetic injections recover position within 3.12 m and drift within 0.00758 Hz/s, and the real fixed-responsibility Jacobian is full rank with scaled condition about 55.35 ([conditional Jacobian report](../2026_09_27_ds7_wave2/clock/REPORT.md)). Those checks show numerical recoverability near one donor solution; they do not show that DS7 contains clock drift or that two receiver slopes are physical.

Existing frozen observations and banks can support one predeclared real-data shadow run with: exact zero replay; a complete mixture-gradient check; shared-slope and, only if topology permits, two-slope forms; common capture-time origin; native-Hz/s to exported-Hz scaling; responsibility-change reporting; constraint removal; and training-fit/frozen-held prediction. It must remain quarantined from geographic scoring and model selection.

True external blockers for adoption are receiver serial/path and oscillator topology, hardware-epoch identity, an independently measured drift-rate bound over capture-length intervals, and evidence separating receiver drift from sample-time warp, LNB drift, emitter drift, and estimator bias. Without these, the coefficient must remain an unshared per-capture frequency nuisance rather than a calibrated clock state.

## 4. Extend known-pilot CFO evidence before changing the geolocation input

The [final CFO receipt](../2026_09_27_ds7_wave2/cfo/FINAL-CFO-RECEIPT.md) supports ordinary and robust known-pilot profiles on one 11.44 GHz lane and one held visit per receiver. Real held coherence exceeds a deterministic phase-scramble control, while differential phase is rejected for reaching the frozen ±2 kHz boundary. The [lane correction](../2026_09_27_ds7_wave2/cfo/LANE-CORRECTION.md) explicitly rejects transfer to the 11.19 GHz visit. The [frequency-units audit](../2026_09_27_ds7_wave3/frequency-units/README.md) proves the baseline export is dealiased and normalized to 11.2 GHz even though cached `fractional_tracking_cfo_hz` is native physical Hz.

Existing cached IQ and public readers can support a separately leased, predeclared expansion to more captures only where receiver, channel, RF, pilot, alias, and track membership are continuous. Required evidence is repeated held-pilot improvement against the same waveform objective and negative control, boundary-free estimates, exact mapping into exported track epochs, and comparison with the current acquisition-CFO input on identical masks. One capture and one scramble are insufficient to replace the baseline measurement. Cross-channel transfer remains inapplicable unless an emitter/alias normalization rule is frozen independently.

External blockers are independent frequency truth and emitter continuity across captures and lanes. These are needed for accuracy or calibration claims, though additional on-disk held-waveform diagnostics do not require them.

## 5. Deprioritize archived-GP substitution; require a genuinely better orbit product

The [orbit inventory](../2026_09_27_ds7_wave1/orbits/README.md) provides causal Space-Track and third-party GP coverage. A fixed-roster all-archive Space-Track comparison changed 26 candidate slots but moved the first-session solution only 0.0142 m and changed training likelihood by +0.0266, with byte-identical replay ([matched comparison](../2026_09_27_ds7_wave1/orbits/matched-comparison.json)). The third-party mirror is stale, misses one shortlisted object, and is not an independent orbit-product class. This evidence makes another archived-GP substitution a low-priority explanation for kilometre-scale error.

The [repeated-satellite gate](../2026_09_27_ds7_wave1/orbit-hierarchy/REPORT.md) found three candidate repeats across donor/target groups but zero independently asserted identity rows, so it correctly rejected orbit-hierarchy calibration. Existing files can support fixed-roster sensitivity and missing/stale-support audits, but not an identity-conditioned orbital correction.

True external blockers are causal SupGP or provider ephemerides with historical bytes and provenance, plus independently asserted satellite identity or calibration observations. Any future orbit comparison must hold candidate IDs, roster, masks, normalization, nuisance model, and compute budget fixed and report missing support rather than replacing identities.

## 6. Use the frozen aggregation controls as comparators

The [eleven-panel aggregate](group-panels-v1.md) records the scientific joint fit and equal, inverse-RMS², and lowest-RMS-75% controls for every disjoint chronological group. These controls are useful benchmarks for whether a single shared nonlinear position is being harmed by model mismatch. They are not independent geolocation models with calibrated uncertainty, and group08 correctly preserves three abstentions caused by an unqualified boundary single.

The already frozen full-88 controls may be compared with the joint fit exactly as declared. Their result can motivate reference-free residual work, but it must not be used to tune weights, discard the boundary case, invent a new aggregation rule, or select a method on this exposed site. Any proposed aggregation rule needs a predeclared rule and evaluation on independent sites or future captures.

## Recommended order

1. Complete the frozen full-88 run and its deterministic/resource checks without modification.
2. Run the full-88 reference-free residual and held-prediction audit using existing artifacts.
3. If a repeated receiver/time pattern survives that audit, run the quarantined receiver-path slope shadow diagnostic; keep adoption blocked on hardware evidence.
4. Expand known-pilot CFO evidence only on predeclared lane-continuous cached captures.
5. Revisit association/null modeling only with matched compute and synthetic plus held-prediction gates.
6. Revisit orbit modeling only when a causal product beyond archived GP and independent identity evidence become available.

This ordering uses the current on-disk corpus first and reserves external work for the two real blockers: hardware/frequency calibration and independently identified higher-quality orbit data.
