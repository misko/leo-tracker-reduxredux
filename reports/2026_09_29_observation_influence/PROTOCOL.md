# Training-only position sensitivity

Use all nine cached-arm optima from sparse_waveform_position and all original
training observations, candidates and q020 mixture terms. No reference location
or held values rank observations. Compute observed negative score Hessian across
E/N and all eight recording-time parameters using central differences of the
full mixture gradient: steps .001km/.0001s and half those steps. Require positive
definiteness, relative symmetry defect <=.005 and relative step disagreement
<=.005; otherwise retain the failure and do not rank that panel.

Analytically differentiate each track's full mixture parameter gradient with
respect to its training observations, including candidate-weight and signal/
background-responsibility derivatives. Verify its gradient sum against the
original model, and test the observation derivative numerically. Solve
`dx/dy = H^-1 * d(score_gradient)/dy`, profiling timing through the full inverse.
Rank by norm of E/N response in meters per canonical Hz. This is local observed
model sensitivity, not an uncertainty or physical accuracy bound.

Report all observations and an eight-observation per-panel queue at >=5MS/s,
matching the existing waveform estimator's tested rate domain. Report unrestricted
rankings too. Compare the previous eight corrected visits per panel with that
queue and with total squared sensitivity. Squared-response sums assume equal
independent perturbation variance only as a descriptive budget proxy.

For the top eligible observation, audit its analytic cross derivative with a
central ±.1Hz difference of a one-track model. Refit the full model at ±10Hz,
starting at the cached optimum, max100 iterations/160 evaluations. Compare the
symmetric position response with the linear prediction; require relative error
<=5% or absolute vector error <=.005m/Hz. Retain nonlinear/unconverged cases and
do not treat their queue as validated. No data are extracted or measurements
corrected in this experiment. Per-panel cap90seconds, sequential single thread.
