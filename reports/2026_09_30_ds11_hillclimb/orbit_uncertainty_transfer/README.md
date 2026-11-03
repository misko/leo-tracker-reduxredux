# Symmetric revision uncertainty transfers to DS9 residual prediction

The finite symmetric orbit-revision mixture passes its historical held-prediction
gate against both zero correction and a matched linear-direction mixture.
The prior is learned solely from1,123 DS7/DS8 training source groups. Their
capture timestamps precede every DS9 capture. Its weights are sealed before
DS9 held scoring. No DS11 positions or reference errors enter this test.

| DS9 comparison,336 sources with nonzero training revision direction | Source wins | Median gain nats/held row | Mean gain nats/held row | Total gain over all570 sources, nats |
|---|---:|---:|---:|---:|
|Orbit uncertainty versus zero correction|275/336|0.20727|0.55586|8689.42|
|Orbit uncertainty versus matched linear uncertainty|213/336|0.00409|0.12143|3420.04|

Four changed sources tie within the declared numerical tolerance in each
comparison. All570 target sources remain reported, including234 sources without
a nonzero training revision direction. The source-level median advantage over
the linear control is much smaller than the aggregate gain; no uniform benefit
is implied.

The coefficient is shared by tracks with the same dataset/session/conditional
NORAD, across receivers and RF bands. Its support is0,+/-0.01,+/-0.03,+/-0.1,
+/-0.3,+/-1 times the causal older-minus-current Doppler direction. Signs are
equally probable at each nonzero magnitude, so the prior mean is exactly zero.
EM learns only six magnitude probabilities from donor training likelihoods.

| Magnitude | Orbit prior probability | Linear-control probability |
|---|---:|---:|
|0|0.05099|0.05639|
|0.01|0.04158|0.03628|
|0.03|0.19139|0.20891|
|0.1|0.26749|0.25692|
|0.3|0.24815|0.25854|
|1|0.20040|0.18296|

The linear control has the same training RMS per track as the actual revision
direction, with a training-fitted slope sign, and independently learned weights
on the same discrete support. Thus the comparison tests revision shape beyond
simple slope and amplitude. A prior-wide shared mean correction failing in
earlier work does not contradict a symmetric uncertainty mixture succeeding.

This is a conditional residual-prediction diagnostic. Existing fitted geometry
and conditional identities are reused; those exports are not an independent
single-scan positioning benchmark. Track residuals and directions are centered
by their training means, held fixed on held rows. CFO/position uncertainty is
not jointly integrated. A source's own training observations update its
coefficient probabilities; held prediction uses the normalized joint/training
mixture ratio. The prior is discrete, not a Gaussian approximation or calibrated
ephemeris covariance. Its20% mass at the largest orbit magnitude also cautions
against interpreting the chosen support as a precisely estimated physical bound.

Two tests pass for training/held isolation, constant invariance, zero-direction
parity and symmetric support. The complete run exits0 in0.98seconds. Independent
reconstruction verifies3,983 unique track cases and1,693 source groups, expands
the six magnitude weights into11 signed states, and reproduces DS9 predictive
scores within1.37e-12nats. Both EM fixed-point errors are below8.2e-11. Source
bindings and gate arithmetic verify. No new IQ, orbit propagation or position
fit is used.

This result supports a DS11 feasibility step using causal revision directions.
Before geographic fitting, preserve joint source dependence, conditional
satellite-association uncertainty and per-track CFO handling; evaluate how the
finite prior changes position information. Do not turn the fitted historical
residual coefficients into deterministic DS11 Doppler corrections or claim
that an absolute orbit covariance has been calibrated.
