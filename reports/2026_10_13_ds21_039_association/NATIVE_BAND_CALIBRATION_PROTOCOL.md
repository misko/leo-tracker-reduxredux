# DS21-039: matched native band-calibration control

Status: implementation qualified before dataset execution. The combined model, runner and frozen held-prediction suite passes **30 tests**; Ruff checks pass. The [capacity diagnostic](BAND_FUNCTION_CAPACITY_RESULTS.md) found a 13.798 Hz RMS loss when the original shared calibration represents the two separately fitted band functions. Three additional columns close that target, but this does not establish better position accuracy. This experiment tests that specific model limitation. It retains fitted `c` throughout.

## Matched conditions and physical constraints

Use the original DS21-039 training partition, native candidate observations, causal 43-satellite bank, singleton association likelihood, neutral waveform evidence, likelihood weight one, physical timing priors, group-offset priors and original seed-5 local 25 km search disk. Bind the completed band-capacity diagnostic, its source archive and its original refinement/input ancestors. The new experiment has its own source freeze and receipts; historical scopes and receipts remain unchanged.

Compare the unchanged original model with a compatible model adding exactly three coefficients: two receiver-specific low/high drift contrasts and one common low/high RF-slope contrast. At each native candidate time and recorded RF, the additional correction is

`q_RX * 1[receiver=RX] * (high-p_RX) * (native_t-t0) + d * (high-p_H) * (RF-f0)/1e9`.

The two receiver terms are summed. Preserve the original full-training `t0`, `f0` and receiver high fractions `p_RX`; `p_H` is the high fraction under training weights that sum to one per window. The centered RF contrast has the same span as the capacity diagnostic's uncentered high-band RF column. Do not recompute these quantities on held data. Native timestamps, rather than window timestamps, define both drift terms. Original receiver baselines, offsets and alias lifts are applied once.

Keep both the original shared coefficient boxes and coupled effective-band limits. For each receiver, `b_low=b-p_RX*q_RX` and `b_high=b+(1-p_RX)*q_RX` must each lie within ±60 Hz/s. Likewise `c_low=c-p_H*d` and `c_high=c+(1-p_H)*d` must each lie within ±5000 Hz/GHz. Extra safety boxes are ±120 Hz/s for each `q_RX` and ±10000 Hz/GHz for `d`; they do not relax the effective-band limits. Add no Gaussian prior on the three new coefficients. This is a bounded empirical calibration sensitivity, not a claimed hardware law.

Use one combined scaled KKT check covering all 55 parameters, including the original boxes, new boxes, coupled band inequalities, timing constraints and geographic constraints. Do not reuse an audit that treats the original and added parameter blocks independently. Solver success alone does not make an outcome eligible.

## Four fits, then frozen prediction

Use exactly the saved original-all and seven-call refinement-free fitted states as starts in each condition: four optimizer calls, each limited to 20 seconds and 600 iterations. The compatible starts append three zeros to the original two nuisance offsets. Before fitting, verify original objective, likelihood and original-coordinate gradients at both zero-tail starts; the added-coordinate gradient need not vanish. Preserve all source replay and closure results.

Select the original condition by its training objective among eligible stationary original/refined incumbents and its two new eligible outcomes. Select the compatible condition only among its two newly stationary outcomes, using its own training objective. A zero-tail source is not a compatible incumbent unless it has passed the full expanded stationarity criterion through the prescribed fit. Retain failed, timed-out, nonstationary and boundary outcomes. No retry, alternative start or reference-based selection is permitted.

Seal all four fit outcomes, both source oracles and both condition selections before preparing held observations. Then make at most one held native prediction per available selected condition. Freeze position, per-satellite timing shifts and the physical calibration function in its training frame. There is no held fitting, recentering or selection. Check per-window likelihood and satellite/clutter posterior closure against the original marginalized likelihood. Report unavailable selections or failed held predictions explicitly; do not silently drop them.

Seal training and held outcomes before joining the development reference. Report training objective and priors, held NLL on identical observations, effective low/high coefficients, stationarity, constraint activity and position error separately. Compare position to the existing original CH1–4, CH5–8 and CH1–8 results with their initialization provenance. A better frequency fit or lower held NLL alone is not a localization success. The configured reference is not independently surveyed ground truth.

## Qualification and execution limits

Required component checks include zero-tail nesting, finite differences for original and added parameters at distinct native timestamps, active coupled-bound KKT cases, a small actual constrained fit and frozen-function evaluation under changed held centers. Runner checks cover parent/source tampering, complete outcome inventories, selection eligibility, held preparation only after a training seal, failed/orphan rejection and cached reads with no numerical work.

The compatible model and its ports are committed as `50891e5f2`; the tested frozen held-prediction port is `e22f861ee`. The new runner reads the historical parent's verified live/archive source subset, exact input manifest, prepared views and seeds without applying the old validator's ambient-import restriction to newly added code. Its initializers must equal the sealed capacity starts. It requires all three added calibration dimensions to be identifiable before fitting. The source freeze binds the delayed reference reader's source file without reading the reference. Raw returned optimizer states survive a failed diagnostic and remain ineligible for selection.

The full slice, including parent validation, training preparation, source oracles, four fits, held preparation/predictions and final source checks, is capped at 165 seconds internally, TERM at 175 seconds and KILL at 180 seconds. Record the outer launch before validation/preparation and preserve termination evidence on failure. Only one heavy dataset process runs at a time, with BLAS threads fixed to one. Publish the qualified implementation/source identity before execution and retain all outcomes in an immutable namespace. No full-DS21 promotion is authorized by a successful DS21-039 result alone; development transfer precedes a frozen locked-set evaluation.
