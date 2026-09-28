# Independent review: geometry confirmation requirements

## Decision

**Do not promote the original static-geometry result as a positive association improvement.**
S substantially improves on D, but a frozen zero-signal clutter-only baseline scores better than
S in all four evaluation recordings. The present result shows that static geometry suppresses a
harmful signal component and approaches the clutter model. It does not yet show that geometry
extracts useful satellite-frequency evidence beyond clutter.

The nominal T/tilt result remains rejected for the earlier control failures. Nothing in this
audit identifies a satellite, validates an antenna orientation, establishes a physical receiver
order, or improves geographic accuracy.

## Frozen post-hoc null audit

I froze and ran `null_audit.py` against the immutable dataset, result and decomposition hashes.
The audit performs no fit. It preserves the fitted RX clutter intensities, sigma, coefficients,
feature transform, training mixture and raw held population. It computes:

1. a zero-signal Poisson-process set density with the fitted RX clutter intensities;
2. an elevation-only ablation using the fitted S coefficients with north and east set to zero;
3. D and S held scores from the unchanged training mixture, without reception or held updates;
4. paired per-window S-minus-D concentration diagnostics from the primary score path.

The source and test were frozen before execution. The synthetic clutter-density test passed,
Ruff passed, and the run completed in under one second. The output SHA-256 is
`03bffa6d4b51941a260ab4577a9905c3eeb4ef661bf3cae9def440333a4ff07e`.

## Findings

| Contrast | Equal-record mean, nats/window | Positive records |
|---|---:|---:|
| D − clutter only | −1.017445 | 0 / 4 |
| S − clutter only | **−0.016388** | **0 / 4** |
| S − D | +1.001056 | 4 / 4 |
| Elevation only − D | +1.002470 | 4 / 4 |
| S − elevation only | −0.001414 | 2 / 4 |
| Fixed-prior S − D | +0.984924 | 4 / 4 |

The clutter-only comparison changes the interpretation. D is strongly worse than ignoring the
forecast signal. S removes almost all of that loss but remains worse than clutter in every
recording, by 0.0026--0.0334 nats per window. Because the null reuses clutter intensities fitted
jointly with D rather than refitting a null, it is not advantaged by a separate optimization. A
separately fitted clutter null could only make the required comparison more demanding.

The fitted signal probabilities explain this behavior. Across visible evaluation held
component-receiver rows, the quadrature-averaged detection probability has mean 0.467 and median
0.459 under D. Under S it falls to mean 0.021 and median 0.00136; under T it is similarly small.
S therefore behaves nearly like the zero-signal model for most forecasts. Its D-relative gain
does not by itself demonstrate correct frequency association.

The elevation-only ablation reproduces the gain and slightly outperforms full S on average.
North/east LOS terms add no robust held benefit with the frozen coefficients. The unchanged
training-mixture diagnostic remains strongly positive, so the S-minus-D difference is not
created solely by reception-driven track selection. It is principally a change in the
candidate-set likelihood caused by suppressing D's signal probability.

The S-minus-D contrast is not a small set of favorable frequency outliers. It is positive in
752 of 796 held windows. Its equal-record mean remains positive after symmetric one-percent
trimming (+1.0347), dropping the largest absolute window per record (+1.0186), or dropping five
per record (+1.0589). This establishes robustness of the D-relative contrast, while the
clutter-only result establishes that the robust contrast is a rescue from a poor D baseline.

The earlier count/frequency decomposition remains algebraically valid: under the full-history
posterior, S-minus-D is −0.01795 count and +1.01900 conditional frequency. That conditional
contrast is relative to D, whose nominated signal model is harmful. It must not be read as proof
that S frequency predictions beat a target-free null. The direct frozen clutter comparison is
the relevant guard against that inference.

## Model limitations exposed by the null

The model allows at most one signal-origin candidate per receiver and treats all others as
uniform periodic clutter. Its candidate shortlist, CFO, alias mapping and frequency means are
conditional on training-selected nominations. There is no decoded common-emitter label. A low
signal probability can improve predictive density by declining those nominations, without
making any alternative nomination correct.

The fitted clutter intensity is global by receiver, while real clutter can vary by recording,
lane, bandwidth and time. The periodic signal width is selected from a small grid. These choices
make absolute target-versus-null calibration uncertain. Four reused evaluation recordings do
not support a discovery claim or a general physical effect, even where record signs agree.

Posterior component choices remain model assignments. The original audit found that D and S
choose different final argmax components in three of seven evaluation lanes, while S and T use
the same argmax throughout. With no target truth, these changes cannot be scored as correct
associations.

## Minimum next confirmation controls

A new frozen panel or scorer should make the target-free baseline part of the primary decision,
not a post-hoc diagnostic. The minimum design is:

1. **Clutter null as a required comparator.** Fit its permitted nuisance parameters on
   calibration reception only, freeze them, and require S to beat both D and clutter on the
   equal-record held score. Report all three absolute scores.
2. **Elevation-only arm.** Prespecify D, elevation-only and full static LOS as nested arms.
   Require north/east additions to beat elevation-only before interpreting directional geometry.
3. **Target-nomination nulls.** Use frozen frequency-shift or candidate-to-track permutation
   controls that preserve counts, receiver labels, window times, visibility schedules and
   marginal frequency distribution. No control may refit or choose a shift after held outcomes.
4. **Outlier robustness.** Freeze record-level and trimmed/window influence summaries. Require
   the primary conclusion to survive removal of a small prespecified number of largest absolute
   contributions.
5. **Mixture-choice audit.** Report fixed-training-mixture, reception-conditioned and full
   prequential scores. Component posterior movement is descriptive unless decoded or reserved
   target truth is available.
6. **Model adequacy.** Audit candidate-count dispersion and lane/record dependence against the
   Poisson clutter assumption. If materially violated, freeze a richer calibration-only null
   before evaluation rather than letting geometry coefficients compensate.

The next panel supports geometry association only if static geometry beats the frozen clutter
null and nomination-null controls on held data, with the same windows and no refit. Until then,
the truthful result is: geometry nearly removes the loss caused by the Doppler signal model, but
useful target association beyond clutter is unverified.

## Disjoint historical confirmation audit

The frozen scorer was subsequently applied, without refitting, to four historical recordings
that do not occur in the ten-session pilot dataset. I independently recomputed the source
bindings: the frozen model hash is
`aeb6b79d4030644bde28c74be8609e406205df81bf6e351c9d5a2cab21169d8b`, the bound training
dataset hash is `7680b762edc3c3599b65494156f53bb1d60fc9a9edfd7d6fc1914a04a78628f7`, and the new target
dataset hash is `99e4e42fac6341d26f6ebd29cbae905cf52a3fb9f8faf2af989683f2ee8b9968`.
The ten training and four target session sets have zero overlap. The confirmation result hash is
`b67e061154336a97475ca437ce7d5b6ccf39b9eae4aa8b6cb6f05141af154828`.

The scorer validates and reuses the saved sigma, RX clutter intensities, eight feature centers
and scales, and successful D/S/T coefficient vectors. It rejects target/training overlap by
default, never calls an optimizer, and never recomputes a target scaler. Its only reception
operation is the prespecified update of component weights with frozen likelihoods.

The target dataset contains 1,551 paired windows in seven lanes. Evaluation reception counts by
record are 205, 210, 233 and 125. Held denominators are 230, 230, 226 and 92, totaling 778. I
matched every lane posterior to the dataset, reproduced every held total from its one-step
scores, and verified identical denominators across D, S, T, swap and reversal. Every prior,
reception and final log posterior normalizes within `7.11e-15` log units.

I also recomputed the zero-signal clutter Janossy density directly from each receiver's candidate
count, lane alias period and the frozen RX intensities. All four record totals agree with the
stored baseline within `1.3e-11` nats.

| Contrast | Equal-record mean, nats/window | Record signs |
|---|---:|---:|
| S − D | +1.026918 | 4 / 4 positive |
| T − S | −0.005252 | 2 / 4 positive |
| S − clutter | +0.008597 | 2 / 4 positive |

The confirmation reproduces the large S-over-D rescue and again rejects a T advantage. It does
not establish a general S-over-clutter benefit. S beats clutter in two records (+0.0221 and
+0.0380) and loses in two (−0.0231 and −0.0026). Combining the four pilot and four disjoint
confirmation record contrasts with equal record weight gives S-minus-clutter **−0.003896
nats/window**. The honest default remains no positive association promotion.

## Next concrete implementation

The next priority is a target-presence and clutter model that is specified before another
geometry comparison. The current omitted-catalogue `other` mass is not a target-absence model:
it represents shortlist support limits, and it is often numerically zero. The current lane
mixture also chooses one track-by-candidate component for the whole reception-plus-held block.
That is restrictive when a lane can contain target absence, multiple physical episodes, or
different emitters over time. The at-most-one signal candidate assumption inside each receiver
window does not solve this block-level problem.

A minimal implementation should:

1. Build a calibration-only clutter port from prespecified target-negative opportunities, such
   as windows where every frozen component is invisible, with exact exposure accounting. Model
   receiver/lane count dispersion and periodic frequency density, then freeze it before held
   scoring. If no defensible negative population exists, stop rather than label mixed reception
   windows as clutter truth.
2. Add an explicit latent target-presence state distinct from omitted catalogue mass. The
   absent state uses the frozen clutter model. The present state sums the frozen nominated
   track-by-candidate likelihoods. Presence may change by declared physical episode or window;
   one catalogue component must not be forced to explain the entire block unless continuity is
   independently justified.
3. Preserve one generative contribution per paired window. Integrate presence and nomination
   alternatives within that contribution, and keep receiver dependence inside the window.
4. Freeze a target-free primary comparison: present-plus-geometry versus absent/clutter, with D,
   elevation-only, full static LOS, nomination permutation and frequency-shift controls. Require
   improvement over clutter in the pilot calibration/evaluation design and in disjoint records.
5. Report posterior presence separately from conditional nomination weights. Neither is target
   truth without decoded labels. Include calibration and randomized probability-integral/count
   diagnostics so geometry cannot merely compensate for a bad clutter distribution.

This is a small model redesign around the existing candidate-set likelihood and datasets. It
requires no new RF. It directly tests the unresolved question: whether the nominated signal
adds predictive information beyond a credible absent-target process before asking which
geometry covariates improve it.

## Evidence

- `null-audit-launch.json`: pre-execution command and hashes.
- `null-audit.json`: frozen diagnostic output.
- `null_audit.py`: no-refit diagnostic implementation.
- `test_null_audit.py`: analytical clutter set-density check.
- Source artifacts: the immutable geometry dataset, primary result and score decomposition.
