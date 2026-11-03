# Independent-error CFO marginalization feasibility

The original objective profiles a per-track constant CFO with a1MHz Gaussian
prior penalty. This diagnostic integrates that same CFO under the normalized
Gaussian prior, retaining independent Student-t4/100Hz observations. It is
distinct from integrating a shared track scale or changing to contrasts.

Use the first12 lexicographically ordered eligible tracks in each of original
scans0 and16, chosen without reference error or held scores. At the frozen
original IID training endpoint choose each track's training-MAP visible
candidate. Numerically integrate its training residual likelihood over all
real CFO, splitting intervals at residual centers and flanks. Repeat at
1e-8 and1e-10 quadrature tolerances and compare log integrals. Report every
case's correction to its profiled score and compute time; no position fits,
held likelihood, candidate reassociation or calibration is performed.

Analytic broad-prior and multimode/anchor-invariance tests precede data use.
Numerical feasibility requires all24 cases, log-integral agreement within1e-6,
reported relative quadrature errors below1e-6, and no integration warnings.
This is not a performance gate or a claim that MAP-only marginalization is a
complete positioning likelihood. Any later model must integrate all retained
candidates and use a normalized joint/training predictive ratio.
Run once single-thread under90seconds, using no new IQ or orbit data.
