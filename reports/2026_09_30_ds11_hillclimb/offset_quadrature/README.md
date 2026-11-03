# Full-candidate CFO quadrature passes at two original endpoints

All1,426 retained candidates across120 tracks in scans0 and16 are evaluated;
none is pruned for low probability. Candidate integrals at32 versus64 nodes
per interval differ by at most2.28e-13nats and their gradients by3.11e-11 per
optimizer coordinate. The24 frozen adaptive-oracle cases agree within5.69e-14
nats and2.13e-11 in gradient. The declared numerical gate passes.

| Scan | Tracks | Candidates | Order32 integration s | Order64 integration s |
|---|---:|---:|---:|---:|
|0|62|760|0.809|1.921|
|16|58|666|0.768|1.561|

The entire single-thread benchmark completes in6.756seconds. Integration times
exclude document loading, orbit prediction/Jacobian construction and CFO-anchor
profiling; these are endpoint measurements, not end-to-end optimizer runtimes.
Source hashes, candidate counts and per-track convergence summaries verify.

Vectorized Gauss-Legendre rules integrate each finite interval between residual
centers/flanks. Two rationally transformed tails cover the whole real CFO axis.
The independent Student-t4/100Hz likelihood and normalized1MHz Gaussian CFO
prior are unchanged from the adaptive integral. Original visibility masks
enter candidate mixtures; currently invisible candidates still enter the
numerical convergence audit. The CFO profile supplies a coordinate anchor,
not the likelihood value.

Full-mixture gradients at the original training-selected positions are
(-0.002285,0.229346,-0.031171) for scan0 and
(0.163594,-0.374287,-3.235350) for scan16, in E-km/N-km/timing-second coordinates.
Thus the original profiled endpoints are generally not stationary for the
marginal objective. These values alone do not predict an improvement in
geographic error or identify a new satellite assignment.

Two tests pass against adaptive integration, including coincident observations,
separated modes, an offset near the prior scale, and changed quadrature anchors.
Endpoint convergence does not guarantee convergence everywhere an optimizer
may travel. A bounded fit should retain all candidates, independently audit
endpoint derivatives and32/64-order agreement, and seal qualified training
selections before geographic scoring. A held predictive evaluation must use
the joint/training integral ratio rather than a training-fitted fixed CFO.
No position optimization, held score, reference coordinate, new IQ or orbit
update is used here. This benchmark promotes no estimator.
