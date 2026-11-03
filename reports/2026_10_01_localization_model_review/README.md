# Localization model review and small numerical prototypes

2026-10-01. Scope: DS9/DS10/DS11 independent single scans, unknown satellite
associations, uniform Sacramento 250 km horizontal prior, user-specified fixed
100 ft (30.48 m) mean-sea-level height. Recommendation: retain the joint robust
greedy estimator as the control; make its evaluations cheaper, then compare
hard and soft association while preserving a few distinct spatial solutions.
The online Gaussian-mixture formulation is a sensible later extension, once
likelihoods and uncertainty have been checked.

This review adds exact algebra prototypes and bounded diagnostics. It does not
replace the frozen experiment, implement a new end-to-end estimator, or claim
improved scan accuracy. Existing recordings were read; no RF was collected and
no new orbit propagation or scan-fitting campaign was run.

## What the experiments establish

| Experiment | Accepted / 64 | Median accepted horizontal error | p90 | Interpretation |
|---|---:|---:|---:|---|
| Earlier sequential greedy | 12 | 5,514 m | 191,786 m | Early hard choices and unstable joint geometry were severe problems. |
| Joint Student-t, primary 90 s | 51 | 1,860 m | 4,109 m | Broad initialization and joint refitting produced much more useful solutions. |
| Primary plus one continuation, total ≤180 s | 63 | 2,058 m | 5,899 m | Extra iterations recovered 12 unresolved numerical fits. |

The last unresolved fit converged in a separate post-hoc 14 s polish, with
2,067 m error and 143.7 s cumulative runtime. This is not a retrospective 64/64
result for the frozen two-stage procedure. Its median runtime was 81.6 s and
worst accepted error 12,308 m. All errors are relative to the unsurveyed roof
reference. Error summaries exclude unresolved scans; success rates retain all
64. The new model, prior representation, gates, and convergence criteria changed
together. On the 12 mutually accepted scans, seven errors improved and five
regressed. These are regression results, not untouched validation or multiple
independent geographical sites. See the [frozen results](../2026_10_01_fixed_height_greedy/README.md).

**Supported lessons:**

- Fixing height alone did not fix localization: sequential controls remained
  approximately 264–312 km wrong, even after orbit support was extended.
- Initial sequential updates were too aggressive: 48/64 exceeded 100 km, when
  satellite identity evidence was weak. Joint reassignment makes those decisions
  reversible. A very broad Gaussian followed by a single EKF update is a poor
  approximation to this nonlinear acquisition problem.
- Robust refitting mattered in development. For DS10-F001, a Gaussian objective
  preferred a 25.6 km error mode over a 1.69 km alternative; three tracks supplied
  most of that preference. The Student-t refit reached about 1.54 km. Merely
  rescoring fixed endpoints did not reverse the preference. This supports
  robustness as a hypothesis, not an isolated 64-scan causal ablation.
- Our Student-t uses ν=4 and the old Gaussian covariance as its **scale**. Its
  covariance is therefore twice that scale. Heavy tails and a broader noise
  model changed together. Compare equal-scale and equal-covariance versions
  before attributing all improvement to tail shape.
- The old background model virtually never accepted clutter. Downweighting a
  distorted satellite track and deciding that a track is not represented by the
  satellite catalogue are separate modeling tasks.
- A numerically converged mode does not establish correct satellite identity,
  global optimality, or a calibrated confidence region. Fixed height is an
  assumption; a height-sensitivity study remains appropriate.

Evidence: [baseline diagnosis](../2026_10_01_fixed_height_greedy/BASELINE_DIAGNOSIS.md),
[development controls](../2026_10_01_fixed_height_greedy/DEVELOPMENT_RESULTS.md),
[residual diagnosis](../2026_10_01_fixed_height_greedy/RESIDUAL_DIAGNOSIS.md).

### A correction to the ambiguity interpretation

The previous diagnostic found eight scans with best-versus-second objective
gap <1 and maximum separation among three endpoints >100 km. Those two tests
refer to different pairs. Re-reading all 64 sealed primary receipts shows:

- 18 have a best-versus-second gap <1.
- In all 18, those two endpoints are separated by <577 m; many are effectively
  duplicates. Twelve pairs have both fits numerically converged.
- **Zero** have gap <1 and best-versus-second separation >100 km.

The distant endpoint was not the nearly tied runner-up in those eight cases.
This does not rule out missed distant modes, but it removes one apparent piece
of evidence for them. Deduplicate converged basins before interpreting runner-up
scores or mixture weights. Never give one basin extra posterior mass simply
because several seeds found it. The original diagnostic remains untouched;
the corrected pairwise measurements and receipt hashes are in
[diagnostics.json](diagnostics.json).

## What the literature contributes

These are primary sources. The proposed adaptations below are our inference,
not implementations validated by those authors on DS9/DS10/DS11.

| Source | Relevant result | Consequence and limitation here |
|---|---|---|
| [Psiaki, 2021: carrier-Doppler LEO navigation](https://onlinelibrary.wiley.com/doi/abs/10.1002/navi.438) | Joint position, velocity and clock estimation with a high-fidelity Doppler model; ideal precision analysis supports meter-scale possibilities. | Joint nuisance estimation has a sound basis. Those absolute-Doppler precision assumptions do not establish meter accuracy for our unidentified, frequency-offset-projected tracks. |
| [Morichi et al., 2026: damped least squares from MEO to LEO](https://iris.polito.it/handle/11583/3007129) | Line-search damping addresses convergence problems caused by LEO geometry. | Keep accepted-objective line searches and scaled convergence tests. Their simulation convergence is not a guarantee under unknown identity and contamination. Abstract reviewed. |
| [Olson and Agarwal, 2012: networks of mixtures](https://april.eecs.umich.edu/media/pdfs/olson2012rss.pdf) | Max-mixtures provide tractable optimization of ambiguous constraints; max and sum mixtures differ. | Our hard joint mode search resembles a max-mixture. A soft likelihood is a different statistical objective, not just a more patient greedy optimizer. |
| [Särkkä, Vehtari and Lampinen: Rao–Blackwellized data association](https://users.aalto.fi/~ssarkka/pub/rbmcda.pdf) | Separate association hypotheses from conditionally tractable continuous state inference. | Keep a small hypothesis bank and integrate tractable nuisance variables. Our unknown receiver with predicted satellite trajectories differs from tracking multiple unknown targets. |
| [Roth et al., 2017: Student-t filtering and smoothing](https://arxiv.org/abs/1703.02428) | Heavy-tailed filtering can address outliers, with approximations needed for tractable inference. | A robust likelihood is justified; a Student-t plus Gaussian nuisance model is not generally closed under filtering. |
| [O’Leary and Rust: variable projection](https://www.cs.umd.edu/users/oleary/software/varpro.pdf) | Solve conditionally linear parameters inside the nonlinear optimization. | Receiver drift is a natural candidate. Profiling a nuisance and integrating it are distinct; Bayesian evidence also needs determinant terms. |
| [Khairallah and Kassas, 2021: ephemeris closed-loop tracking](https://www.ion.org/publications/abstract.cfm?articleID=18114) | A known reference receiver improves satellite ephemerides and downstream localization. | Orbit error deserves a shared model. Reference-assisted calibration is a separate experiment; using our evaluation GPS to correct the same scan would invalidate a blind result. Abstract reviewed. |
| [Qin et al., timing properties of Starlink Ku-band](https://arxiv.org/abs/2501.05302) | Frame timing has structured jumps, jitter, and imperfect clock discipline. | Consider empirical change points and structured errors. Frame timing observations cannot directly specify the covariance of our carrier-frequency tracks. |
| [Camuzcu, Hoang and Vahid, 2026 preprint: passive beacon navigation](https://arxiv.org/html/2605.20394v1) | Doppler-rate/TLE association followed by EKF sensor fusion. | A useful association strategy, but its known reference frame, aided tracking, and limited hardware beacon updates do not validate blind acquisition from our 250 km prior. Its OFDM-ranging comparison is simulated. |

The literature supports the ingredients, rather than one turnkey algorithm
whose reported accuracy transfers to our measurements.

## A generative model matched to our data

Let x=(E,N) denote horizontal coordinates in the Sacramento-centered regional
map, and D the 250 km disk. Use p(x)=1_D(x)/(π·250²) in these coordinates,
independently for each scan. This is the frozen map-disk prior, not a uniform
latitude/longitude rectangle. Convert to ECEF on the fixed height surface
h_ellipsoid(x)=30.48 m+N_geoid(x).

For stationary receiver position r(x), satellite position r_s(t), velocity
v_s(t), time-tag offset τ and satellite epoch error δ_s, the present geometric
prediction is

\[
 f_s(t;x,\tau,\delta_s)
 =-\frac{f_0}{c}\,v_s(t+\tau+\delta_s)^T
 \frac{r_s(t+\tau+\delta_s)-r(x)}{\|r_s(t+\tau+\delta_s)-r(x)\|}.
\]

This is the existing stationary-ECEF model, not a complete high-precision
propagation model. Our τ is an orbit-query **time-tag offset**, not a carrier
frequency offset. Constant frequency offsets are removed per receiver by a
contrast matrix C_j. For track j,

\[
 y_j=C_j f^{obs}_j,\qquad
 \mu_{js}(x,\eta)=C_j f_s(x,\tau,\delta_s)+B_j\beta,
\]

where β holds the two receiver drift terms and η denotes all shared nuisances.
The current implementation selects at most eight samples per track; these
contrasts contain shape information, not calibrated absolute Doppler. More
samples can help only with a defensible correlation model.

Each complete physical track has one latent assignment z_j, including a
background label 0. Define normalized detection/association probabilities
a_js(x), with a_j0+Σ_s a_js=1. Visibility is part of these probabilities, not
proof of identity. Let b_j be a proper density for unmodeled tracks. Then

\[
 L_j(x,\eta)=a_{j0}(x)b_j(y_j)
   +\sum_s a_{js}(x)\,t_\nu(y_j;\mu_{js}(x,\eta),S_j),
\]

\[
 p(x,\eta\mid Y)\propto 1_D(x)\,p(\eta)\prod_j L_j(x,\eta).
\]

This factorization assumes retained tracks are conditionally independent after
their shared errors are represented. Duplicated observations, common extraction
artifacts, or correlated satellite errors need additional grouping/covariance.
The same satellite may produce several fragments or receiver tracks: do not
impose a blanket one-track-per-satellite constraint. Enforce only independently
justified physical exclusions.

For fixed x,η the satellite responsibility is

\[
 r_{js}=\Pr(z_j=s\mid y_j,x,\eta)
 =\frac{a_{js}(x)t_\nu(y_j;\mu_{js},S_j)}{L_j(x,\eta)}.
\]

Thus Pr(satellite|location) supplies an opportunity prior; the measured Doppler
shape supplies the identity evidence. Both are required. LNB orientation could
eventually refine a_js through a calibrated soft detection pattern, including
unknown roll; an assumed rectangular hard field of view would be unjustified.
Missing catalogue objects must remain possible through background/model-gap
mass. The current fixed-catalogue prior sends invisible-candidate mass to
background; changing that normalization is itself a model ablation.

### Remove an exact timing ambiguity

The likelihood depends on d_s=τ+δ_s only. For any a,
(τ,δ_s)→(τ+a,δ_s−a) leaves all predictions unchanged. The data cannot separate
those terms in this model; their priors determine the split. Verified on all
50 tracks and 1,102 candidates in DS9-F001: shifting by 0.375 s changed finite
branch log scores by at most 1.43e−14.

If τ∼N(0,σ_τ²) and independent δ_s∼N(0,σ_δ²), eliminate τ exactly:

\[
 d\sim\mathcal N(0,\Sigma_d),\qquad
 \Sigma_d=\sigma_\delta^2 I+\sigma_\tau^2\mathbf1\mathbf1^T.
\]

For M effective shifts, mean d̄, the prior quadratic and determinant are

\[
 d^T\Sigma_d^{-1}d=
 \frac{\sum_s(d_s-\bar d)^2}{\sigma_\delta^2}
 +\frac{M\bar d^2}{\sigma_\delta^2+M\sigma_\tau^2},
\]

\[
 \log|\Sigma_d|=(M-1)\log\sigma_\delta^2+
 \log(\sigma_\delta^2+M\sigma_\tau^2).
\]

This is O(M), preserves shared correlation, and removes one redundant likelihood
direction. It does not magically identify clock error or remove nonlinear
dependence on d. Marginalizing the Gaussian clock gives this normalized prior;
profiling it gives the same quadratic, with different normalization. Inactive
variables must be integrated consistently when comparing models of differing
dimension, not simply rewarded for disappearing.

### Collapse genuinely linear Gaussian nuisances

For fixed identities and nonlinear parameters, stack all tracks together:

\[
 y=g(x)+Ba+\epsilon,\quad a\sim N(0,P),\quad \epsilon\sim N(0,R)
 \implies y\mid x\sim N(g(x),R+BPB^T).
\]

Receiver drift is linear. Effective epoch perturbations are only locally
linear, so their collapse requires a checked local approximation. The shared
matrix BPBᵀ has cross-track blocks; separately inflating each track covariance
is not equivalent. Nor may we replace ∫p(η)∏_j L_j dη with a product of separate
integrals that each give a track its own fresh clock.

After whitening, U=L_R⁻¹BL_P and e=L_R⁻¹(y−g), factor only
G=I+UᵀU. With â=G⁻¹Uᵀe,

\[
 \log p(y\mid x)=-\tfrac12[
 \|e-U\hat a\|^2+\|\hat a\|^2+\log|G|+n\log(2\pi)]
 -\log|L_R|.
\]

This exact Gaussian identity includes the complexity penalty log|G|. Minimizing
the residual alone is a profile objective, not integrated evidence. With a
Student-t signal, Gaussian elimination is exact **conditional on** its latent
precision and identity; integrating both still requires approximation or
sampling. Substituting an expected precision does not make that marginalization
exact. [kernels.py](kernels.py) implements the two exact Gaussian identities.

## Three practical estimators, in order

### A. Faster joint robust greedy control

Keep the existing hard assignment objective and broad acquisition. At each
iteration: score identities; choose the best branch per track; take a damped
robust joint step; revisit identities. Replace objective-only evaluations with
mean-only evaluation; compute derivatives only for the branches used in the
step. Share orbit/height calculations, cache constant contrast covariances, and
use selected-satellite rather than full-catalogue finite differences. Audit
mean/score/Jacobian equivalence at diverse locations and horizon boundaries.

Replace the current mixed-unit step tolerance with a declared scaled state
norm, plus objective and gradient criteria. Allocate remaining wall budget to
unresolved winning basins rather than arbitrary per-seed iteration caps. These
are separately versioned numerical changes, not excuses to relax acceptance.

### B. Soft association with a small bank of distinct modes

Compare the hard objective, −Σ_j max_s log[a_js p_js], with the soft objective
−Σ_j logsumexp_s log[a_js p_js], adding the shared prior once. Keep background
in both. Never average geographically distinct solutions into one Gaussian.

A generalized EM/IRLS iteration computes responsibilities r_js, then weights

\[
 \lambda_{js}=\frac{\nu+d_j}{\nu+
 (y_j-\mu_{js})^T S_j^{-1}(y_j-\mu_{js})},
\]

and takes a damped least-squares step with weights r_js λ_js. Freeze these
weights for that inner step and accept against the **actual soft objective**.
Location-dependent association priors also belong in the objective and gradient;
hard visibility boundaries need explicit treatment. This is local optimization,
not a guarantee of the globally correct mode.

Initially keep three distinct basins, increasing only when measured ambiguity
justifies it. Gating can retain high-responsibility identities plus background,
but must account for omitted probability mass and periodically rescore the full
catalogue. Renormalizing an arbitrary top-k subset exaggerates confidence.

Fit scores are not posterior mode probabilities. For an isolated interior mode,
a Laplace approximation uses exp(−J_k)(2π)^(q/2)|H_k|⁻¹/², including nuisance
integration and priors. H_k must approximate the actual posterior curvature,
not blindly reuse the IRLS normal matrix. Boundaries, overlapping basins, weak
directions, and unresolved fits require more care. A simple normalized
exp(−J_k) should be labeled a relative fit score.

### C. An online mixture after acquisition

The user's Gaussian-mixture idea is appropriate **within localized basins**:

\[
 p(x,\eta\mid Y_{1:j})\approx
 \sum_k w_{kj}\,\mathcal N(x;\mu_{kj},P_{kj})\,
 p_k(\eta\mid x,Y_{1:j}).
\]

For a new independent track compute the predictive evidence
Z_k=∫L_j(x,η)p_k(x,η|Y_{1:j−1}) dx dη and update w_k∝w_k Z_k.
Branch components when associations imply genuinely different locations;
merge only compatible modes and nuisance histories. Keep shared nuisance
cross-covariances or conditional information factors. A modest global mesh
starts acquisition; large local Gaussians alone are not an exact uniform disk.

This is a Rao–Blackwellized hypothesis filter: analytic conditional updates
where possible, a small explicit bank for nonlinear/discrete ambiguity. Every
single-scan benchmark still resets the original prior. A continuation refits
existing evidence; it is not a new measurement update. Completed-track replay
is also not equivalent to online processing of future-unavailable track samples.

## What the bounded speed tests say

On the saved DS9-F001 state (50 tracks, 1,102 catalogue candidates), the existing
vectorized all-candidate scorer took **0.090 s**. Computing just the 50 selected
densities through the derivative-producing interface took **0.902 s**, with
scores agreeing to the diagnostic tolerance. The profile recorded 500 calls to
the full-catalogue prediction helper, consuming 0.879 s cumulatively. This is
one profiled, cold-cache state, not a fitted-scan timing comparison. It directly
supports separating means from Jacobians and avoiding repeated catalogue
predictions. See [profile](fixed-state-profile.txt).

The exact collapsed Gaussian kernel took **0.040 ms**, versus **1.380 ms** for
a dense covariance oracle, on a synthetic 300-row/24-nuisance problem (15
repeats, median, one BLAS thread). Log densities agreed within 2e−13: about
34.6× for this kernel. Whitening was assumed available. The present greedy
solver already solves a relatively small active system, so **this is not a
34.6× improvement over the existing localization code**. Its main value is
making properly marginalized alternatives affordable.

The 21 owned tests cover independent dense numerical oracles, rank deficiency,
inactive nuisance integration, the failure of independent noise inflation,
determinant penalties, and invalid inputs. These algebra tests say nothing yet
about geographical accuracy. Reproduce with:

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src .venv/bin/python -m pytest -q reports/2026_10_01_localization_model_review/test_kernels.py
```

`diagnose.py` verifies receipt seals and binds sources/inputs, then refuses to
overwrite its existing JSON output. The profile and kernel benchmark are
development diagnostics, not golden fixtures.

## A discriminating evaluation plan

1. **Speed without changing the model:** compare mean-only and selected-branch
   derivative implementations against the current objective/Jacobian on a
   bounded three-scan panel. Measure orbit calls, objective calls, iteration
   count, wall time, and final objective differences. A useful initial target
   is a ≥2× end-to-end reduction with no scientific regression; unproven today.
2. **One change at a time:** retain the 64 fixed recordings and acquisition
   seeds, then compare hard versus soft assignment, equal-covariance Gaussian
   versus Student-t, and existing versus calibrated background. Report every
   attempted scan, including unresolved fits, rather than only the best errors.
   Schedule this as bounded batches after the small prototype passes, not a
   long campaign hidden inside this review.
3. **Model sensitivity:** vary height in a predeclared plausible neighborhood
   of 100 ft MSL; inspect clock/epoch prior sensitivity; compare correlated noise
   and sample counts. Diagnose position information after nuisance elimination
   using H_xx−H_xη H_ηη⁻¹ H_ηx. Small eigenvalues expose weak directions; they
   do not by themselves prove calibrated covariance or physical bias.
4. **Truthful association and uncertainty:** synthetic known-identity cases,
   wrong/missing catalogue objects, coherent shared timing perturbations, and
   track corruption; then calibration on held-out sessions/locations. Report
   coverage of 50/90/95% regions, multimodal region size, and catastrophic-error
   rate. Satellite identity accuracy needs independent labels, not the selected
   fit's own residuals. Split adjacent scans together to limit leakage.
5. **Promote only after evidence:** frozen regression target is at least the
   existing acceptance rate, roughly 2,058 m median and 5,899 m p90, with lower
   runtime; better accuracy is an experimental question. Stronger validation
   needs different sites and realistic nuisance errors. Do not tune model
   priors from the same scans' evaluation coordinates and call the result blind.

The next implementation should therefore improve the existing physics
evaluation path first, introduce one soft-association alternative second, and
add an online hypothesis filter only when its uncertainty and computational
benefit have been demonstrated.
