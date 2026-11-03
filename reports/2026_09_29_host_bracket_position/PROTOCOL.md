# Shared host bias with measured per-record capture brackets

Freeze before fitting. All nine DS7–DS9 early/middle/late eight-scan panels,
unchanged full q020 trend mixture, all 4,328 bank-eligible tracks. Compare against
the inherited free per-record timing fits; replay their training and held scores.

Parameterization: east/north, one shared bias b, eight deviations e_i within
each measured first-sample host bracket relative to its midpoint. tau_i=b+e_i.
Keep position bounds +/-12 km. Bound b to [-5-min(lo_i),5-max(hi_i)] so every
permitted tau remains in the original [-5,5] state bank. This slightly trims
otherwise feasible combinations near the global bank limits; report bias-bound
contact. b/e decomposition can be nonunique and is not a calibrated clock estimate.
Constant host UTC bias within each panel is an assumption, not evidenced discipline.

Three starts: inherited position, b=median(free taus)+{-0.25,0,+0.25} seconds
clipped to its bounds, deviations clipped from free taus minus b. L-BFGS-B with
analytic parameter-chain gradient, maxiter100/maxfun160, ftol1e-13, gtol1e-6,
maxls25. Select greatest training score among successful starts with projected
loss gradient <=0.01 and position/bias away from bounds by 0.001. Capture-deviation
bound contact is allowed and counted. No held or geographic outcome selects fits.

For the selected fit audit transformed gradient with feasible finite differences
(position1e-4km; bias/deviation1e-6s); tolerance0.02. Preserve failed audits and
unqualified panels, do not silently report partial medians. Record every start,
full held rows, original baseline score, geographic error to the same previously
exposed unsurveyed reference, and all active capture constraints. A benefit must
include geography as well as held prediction; no absolute-UTC or sub-km validation
claim follows from this assumption-dependent sensitivity model alone.

Three synthetic tests before execution. One child per panel, sequential, one
numerical thread, 120-second cap per child, no retries or new RF. Check all declared
artifact hashes and measured timing bindings. No production changes.
