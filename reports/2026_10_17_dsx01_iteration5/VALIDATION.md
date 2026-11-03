# Recovery evidence and the next prediction tests

The goal is a single position-independent method recovering a larger fraction
of DSX01's 15 windows, with useful whole-scan associations and lower position
errors. Higher development-set counts alone do not satisfy that goal.

The latest complete fitted-c development lead assigns 462/693 requested points,
versus 96/693 originally, and strongly restores eight windows. It adds a
constant per-satellite frequency residual. Its excluded-half conditional
residual prediction is negative in 39/40 fits across both c arms. Therefore it
is descriptive evidence, not a model to promote. The other complete new model,
expanded-bank width continuation, improves total support but reduces requested
support from 434 to 429. Preserve these negative results.

## Distinct questions, distinct experiments

1. **Full-data recovery:** same 693 original winning observations and all
   20,084 whole-scan observations. Keep missing estimates in denominators.
   Report all 15 windows, original-support new/lost/intersection RMS, timing,
   strict endpoints and configured-reference position separately. Original
   labels are model outputs, not verified satellite identity.
2. **Conditional residual transfer:** hold fixed the same full-data-conditioned
   physical/calibration/q baseline; learn only a new residual term on one half
   and evaluate actual excluded-row likelihood on the other. This isolates
   whether the new correction transfers. It is not cold validation and does
   not establish geographic accuracy. Never use a masked common.measure NLL:
   that helper's NLL remains full-data even when its counts are masked.
3. **Half-recording cold prediction:** discover candidates, calibration and
   position using complete first-half probes only, with public production
   policy and causal TLE selection. Predict the second half with declared
   residual-clock extrapolation and only training-selected IDs. This is a
   forecasting assay; satellites absent from the training bank cannot recover
   their later trajectories. Original full-data labels can diagnose bank
   overlap but cannot certify identities or supply new inference candidates.
4. **Blocked cold interpolation:** deterministic alternating 20-second blocks
   measured from the immutable device-counter origin. Keep whole probes;
   exclude and count boundary straddlers. Parity 0 is the declared first pilot,
   S03 is the existing validation source, and neither is selected from model
   outcomes. Learn discovery/calibration/position from retained probes only.
   This tests missing temporal segments while allowing training evidence
   throughout the capture. It does not replace the forecasting assay or prove
   generalization to a new location. Publish actual resulting denominators.

Every derived training payload must be invariant to perturbing every excluded
candidate's CFO, score and gate. Preserve source timing authorities and probe
IDs. Freeze prediction/calibration before reading held CFO for evaluation. Use
actual normalized held likelihood, assigned coverage and residuals; improved
association percentage alone can reward false matches.

The original public production entrypoint fits c throughout. A downstream c=0
continuation is conditional sensitivity, not an independent c=0 cold pipeline.
Subsequent model comparisons must match their observations, candidate sets,
priors and search allowances in fitted-c/c=0 arms wherever c is used. Report
frequency-fit effects separately from position accuracy.

## Age-aware relative timing investigation

Use each satellite's element epoch and provider, not snapshot download age.
Common receiver/recording clock uncertainty remains separate. Historical
calibration uses only snapshots collected before the earliest DSX recording,
no RF observations, target timings, configured position or named target IDs.
Newer TLEs are consistency references, not truth. Preserve identical/reversed
element epochs, invalid propagations, heavy tails and perpendicular errors.
An unsupported age/provider region receives an explicit fallback, not a
fabricated precise uncertainty. Freeze width rules before localization fits.

Heterogeneous relative penalties must respect the original zero-sum basis;
changing a single satellite's total shift changes the common mean and every
relative shift. Candidate profiles must use the exact weighted penalty, and
scalar width 2 seconds must nest the original objective and gradients. Raw
objectives across different prior widths are not Bayesian model evidence when
normalization constants are omitted.

## Promotion and completion

No per-window selection, union of incompatible winners, hand-chosen satellite
IDs, reference-position initialization or reference-distance-based selection.
No numerical threshold relaxation. A strict optimizer endpoint establishes
stationarity under the model, not correct identities or correct location.

After a model earns excluded-data support, freeze one global policy before
broader existing-corpus evaluation. Include full DSX01 and the established
DS21/DS22 fast cohorts with all missing cases visible, using the existing
position-error CDF format. These datasets were already explored; do not call
them unseen. Additional known-position sites are needed to demonstrate
geographic transfer; one station's temporal holdouts cannot establish it.

All work uses the existing corpus, bounded iterations, unchanged scientific
fixtures and read-only archives. No new RF collection, production deployment
or remote publication is authorized by this research continuation.
