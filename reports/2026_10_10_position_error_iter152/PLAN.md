# Proper nuisance integration: mathematical preparation only

No tests, benchmarks, recording evaluations, fits or reference queries are authorized or executed here. The parent must review the mathematics and allocate capacity before even the prepared synthetic tests run. No runtime B7 adapter is proposed yet.

## Actual two-dimensional block

[DynamicRFObjective](../../src/leo/analysis/hard60_dynamic_rf.py) gives each receiver's smooth-clock coefficients the same proper precision

`P = (I/50² + D2_null.T D2_null/25²)/4²`.

The clock basis has already removed constant and linear node modes. Its identity term makes P positive definite. [SatelliteCorrection](../../src/leo/analysis/hard60_satellite_correction.py) preserves this precision block, and [SlopePrior](../../src/leo/analysis/hard60_slope_prior.py) changes only the distinct satellite-slope block. Consequently select one existing smooth-clock prior eigenmode per receiver: the unique lowest-eigenvalue mode of P, determined from the model basis and prior only. No data/residual/reference-dependent direction is allowed. Require a nonempty block and a numerically separated smallest eigenvalue; reject an ambiguous eigenspace rather than choose its direction using data. Eigenvector sign changes cannot change the integral.

Write each receiver's coefficients as `b_r = q a_r + b_perp,r`, with unit eigenvector q, q.T b_perp,r=0 and eigenvalue λ>0. The selected amplitudes a=(a0,a1) have normalized unbounded Gaussian prior `λ/(2π) exp(−λ a.T a/2)`. Other eigenmodes, affine receiver terms, static c, RF-time terms, timing shifts and satellite slopes remain fixed for this conditional diagnostic. This is integration of existing parameters, not an added correction. The same smooth block exists in both final c arms. In contrast, selecting the two RF-time coefficients would disappear in c=0 and is not this proposal.

The actual optimizer constrains original smooth coefficients to ±2000. Do not silently discard this domain. For each receiver, intersect `−2000 ≤ q_j a_r + b_perp,r,j ≤ 2000` to obtain an exact amplitude interval. Empty or zero-measure intervals fail admission. Two receivers yield a rectangle. A later exact conditional integral includes this indicator. Do **not** divide by its conditional prior mass: that mass can change when the fixed other coefficients change. Global normalization of a consistently truncated full prior is constant, but conditionally renormalizing each slice would change the model.

## Observed mixture curvature

At fixed geometry, timing, visibility and component weights, let component mean be `μ_ik(a)=μ_ik(0)+A_ik a`, residual `r_ik=y_i−μ_ik`, and responsibility w_ik under the normalized Gaussian-plus-clutter likelihood. For each Gaussian component define `s_ik = r_ik A_ik / σ²`. Clutter has score and curvature zero. Then

`g = −Σ_i E_w[s_i] + Λ a`

`H = Λ + Σ_i E_w[A_i A_i.T / σ²] − Σ_i Cov_w(s_i)`.

The covariance is over **all** components, including clutter's zero score. Omitting it gives complete-label curvature, not the observed Hessian. It can make H indefinite even when Λ is positive definite. No clipping, pseudodeterminant or arbitrary ridge is allowed. Wrapped Gaussian winding components can be included as explicit mixture components; the prepared finite-mixture helper is an analytic oracle, not a replacement implementation of the production wrapped likelihood. Geometry-dependent detection terms are constant with respect to these amplitude coordinates, but must remain in any eventual spatial objective.

For an interior, isolated conditional mode and an effectively unbounded domain,

`F_Laplace = F_MAP + 0.5 log det H − 0.5 log det Λ + constant`.

Constants are common only within a fixed bank/model/block. Under invertible amplitude coordinates a=Tz, both H and Λ transform by T.T (…) T, so their log-determinant difference is invariant. An unnormalized Hessian determinant by itself is not invariant to units. The full prior factor of the fixed other coefficients must remain in F_MAP.

For active/near boundaries, multiple modes or indefinite curvature, the displayed Laplace expression is not admitted. A two-dimensional normalized-prior quadrature over the exact box slice is the appropriate oracle, retaining all mixture terms. It does not require a fitted covariance interpretation or new prior width. An exact integral may exist when single-mode Laplace fails; that does not authorize repairing Laplace numerically.

### Receiver separation reduces the oracle to two one-dimensional integrals

For this specific conditional block, the apparent two-dimensional problem
factorizes. `clock_design` multiplies each receiver's smooth basis by its receiver
indicator. Each observation therefore depends on only a0 or a1; the likelihood
sums independent observation NLLs and the selected prior has diagonal precision.
With all other variables fixed and the exact box slice a rectangle,

`F(a0,a1) = C + F0(a0) + F1(a1)`.

Consequently the normalized conditional integral is the product of two bounded
one-dimensional integrals, and the observed conditional Hessian has zero mixed
entry. This remains true with satellite mixtures, wrapped components, clutter
and multimodal receiver likelihoods, provided these retain the current
per-observation factorization. Two adaptive 1D quadratures are therefore the
preferred oracle; a dense 2D grid would add cost without information. The
arbitrary-design 2D helper remains a derivative test oracle, not a requirement
to implement expensive 2D integration.

This separation does not hold after jointly integrating or reoptimizing shared
position, timing or satellite parameters, nor under a future correlated
receiver likelihood. Verify the zero mixed derivative and a product-integral
identity before a recording adapter is admitted. Count fixed penalties once
through C, and retain the selected normalized prior factor once per receiver.

## When it can matter, and fixed stop conditions

With known Gaussian labels, a fixed linear design and fixed prior, `H=Λ+A.T W A` is independent of position. Its unbounded determinant correction is constant: unbounded integration and profiling then have identical position-score differences. This no-op is not exact for a finite coefficient box. Even when the mode is interior and the box is fixed, the posterior Gaussian mass inside that box can vary with the residual and hence position. For the selected smooth-clock mode the design depends on observation times/receiver, not position. Variation under the actual bounded mixture can therefore come from responsibilities/residuals and their missing-information covariance, or from boundary mass (including slice changes as other coefficients change), not newly acquired geometric information. Neither 117's degeneracy nor 144's nuisance-span fraction proves it improves position accuracy.

Before any recording work, the prepared tests must pass: analytic Gaussian integration, finite-difference observed-mixture derivatives, basis/units invariance, exact coefficient-box geometry, and explicit indefinite-Hessian rejection. These are source-only and unexecuted at preparation.

For a separately authorized diagnostic, first fix the same original endpoints and common block policy across all consumed panel members and both c arms. Do not optimize position or choose blocks per scan. Compare a bounded, globally declared ordinary position-stencil with its conditional modes and exact 2D quadrature. Before freezing that diagnostic, define the stencil and quadrature convergence rule. Predeclared screening conditions here are: (a) quadrature numerical error below 1e-4 NLL; (b) require at least 0.01 NLL variation in the integration-minus-profile correction across the fixed stencil to call it nonconstant; (c) admit Laplace as a cheap substitute only if its relative score differences agree with quadrature within 1e-3 NLL across every member/arm/stencil point. Any failed coverage or violated approximation condition blocks promotion of this simple approximation. These are numerical relevance/accuracy tolerances, not position-error-tuned parameters, and establish no localization benefit.

If the correction is effectively constant, stop. If it varies only at unstable assignment/boundary changes or requires broad multimodal integration, stop the proposed lean Laplace route. Only a subsequently frozen matched-c position comparison can establish improvement. No parameter choices, validation claims or recording experiment are authorized by this mathematical preparation.
