# Four-scan training, four whole scans held out

Freeze before outcomes. Split each existing eight-scan panel into its first four
and last four scans, testing both directions. Source fits use BOTH receivers
but only original source training samples. Hold all measurements of all target
scans out of initialization, optimization, grouping, and model selection.

Baseline: three fixed starts E=-2,0,2km, N=0, four timing offsets zero, same
origin and bounds as before. Select the highest source training score among
qualified starts. Compare the fixed0.5 Hz/s shared candidate-slope arm, grouping
only from source-baseline training probabilities, initialized at that baseline.
Reuse receiver-holdout fit limits and gradient qualifications, and slope model
128/256-node audits. No other scale is selected after this comparison.

Target evaluation uses the ORIGINAL q020 complete-track likelihood. Integrate
the JOINT likelihood of ALL tracks in each target scan over ONE shared timing
offset, with a normalized uniform prior on[-5,+5]seconds. Sum independent
scan log integrals. Do not profile timing, integrate each track separately, or
fix timing to a target-informed optimum. The location remains source-fitted.
This is a plug-in location comparison under a fixed timing prior; source
parameter uncertainty is not integrated.

Use composite Gauss-Legendre quadrature in each0.25-second bank interval,
16 nodes per interval, audited against32; require absolute log-integral change
<=0.01 for every scan. Reimplement batched prediction only for evaluation and
require scalar original-model replay at bank endpoints and interior times
within1e-7 log-score units. Fail explicitly if no visible candidate exists.
Per-panel/direction cap120seconds, three CPU workers maximum. Retain failures.

Existing conditional candidate exports and an exposed one-site reference limit
claims of blind inference or general geographic accuracy. Future-to-past and
past-to-future directions are dependent diagnostic comparisons.
