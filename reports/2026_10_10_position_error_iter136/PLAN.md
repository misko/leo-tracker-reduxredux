# Correlated frequency errors: a score audit before fitting

This preparation proposes a soft, reference-free audit of frequency-error correlation. It changes neither production B7 nor satellite-label persistence. No correlation parameter is selected or fitted, no position error is evaluated, and no recording/model calls have run. The first screen is the derivative at zero correlation, using predetermined pairs and ordinary saved endpoints in both c arms.

## Existing evidence

[Iteration 87](../2026_10_09_position_error_iter87/RESULTS.md) completed all 148 DS16/17/18 members. Conditional within-RX/satellite/channel adjacent residual correlations, for gaps up to 2 seconds, had pooled medians 0.261 fitted-c and 0.363 c=0 over 8,072 eligible groups. The grouping used fitted-derived maximum labels and duplicate averages. These are descriptive correlations, not covariance estimates for independently acquired measurements.

[Iteration 90](../2026_10_09_position_error_iter90/DECISION.md) reduced median absolute satellite receiver contrasts from 23.944 Hz to 1.874 Hz after projecting the existing smooth-clock span. That concerns conditional means rather than covariance, but warns that clock structure can masquerade as satellite effects. [Iteration 17](../2026_10_08_position_error_iter17/README.md) rejected density weighting: fitted mean 1.004952 km became 1.012704/1.025073 km; worst 2.835 km became 4.122/4.285 km. [Iteration 110](../2026_10_09_position_error_iter110/DECISION.md) changed label persistence, not measurement covariance: fitted mean 1.117359 km became 1.083074 km, median 0.905836 km worsened to 0.914724 km, and six members improved while six regressed. Its screening rule failed.

## Preserve B7's singleton-event probability

For row i and candidate k, let v_ik be visibility, r_ik the circular residual, L the alias period, sigma the existing frequency scale, lambda the clutter rate, and a=q/(1-q), where q=detection_budget/K. B7 uses

```
T_i = lambda/L + sum_k a*v_ik*phi_sigma(r_ik)
p0_i = exp(-lambda)*(1-q)^(sum_k v_ik)
A_i = p0_i/(1-p0_i)
B7_i = A_i*T_i
```

The row integrates to the conditional singleton-event mass, not 1:

```
W_i = lambda + a*sum_k v_ik
M_i = A_i*W_i
pi_i0 = lambda/W_i
pi_ik = a*v_ik/W_i
f_i = pi_i0/L + sum_k pi_ik*phi_sigma(r_ik)
B7_i = M_i*f_i
```

The normalized frequency mixture f_i integrates to 1. M_i is the probability of exactly one detection conditional on a nonempty observation under the existing clutter/detection model. Retain it unchanged; dropping it would silently change the geometry-dependent cardinality/visibility likelihood. These expressions follow [hard60_score.likelihood](../../src/leo/analysis/hard60_score.py).

## A normalized pair mixture in O(K)

For a pair(i,j), retain independent label priors. Replace only the emission product when both observations have the same satellite label:

```
F_rho = f_i*f_j
        + sum_k pi_ik*pi_jk*(phi_rho(r_ik,r_jk)
                            - phi_sigma(r_ik)*phi_sigma(r_jk))
pair_likelihood = M_i*M_j*F_rho
```

All cross-satellite, signal/clutter and clutter/clutter products retain independent emissions. Each component density integrates to 1, so F_rho is normalized. At rho=0 it is exactly the independent B7 product. A future implementation must branch directly to ordinary B7 at rho=0 to preserve its score and gradients without floating-point rearrangement. Unpaired observations remain ordinary B7; no row is discarded or counted twice. This changes conditional measurement errors, unlike iteration 110's label-transition prior.

The O(K) construction specifically assumes correlation conditional on a repeated satellite component. It could represent component-specific temporal error, but is not a general receiver-wide oscillator covariance: a receiver-wide error could correlate two signal measurements even when their satellite labels differ. Giving every different-label emission the same correlated Gaussian generally requires O(K²) exact marginalization. The proposed screen tests only the stated same-component mechanism; its results must not be presented as a general LNB/clock covariance measurement.

For standardized residuals z_i=r_i/sigma and z_j=r_j/sigma, the unwrapped same-label density is

```
phi_rho = exp(-(z_i*z_i - 2*rho*z_i*z_j + z_j*z_j)
              /(2*(1-rho*rho)))
          /(2*pi*sigma*sigma*sqrt(1-rho*rho))
```

The determinant term is essential. Simply penalizing differences or discounting a row does not implement this model.

### Stable positive evaluation

Do not compute f_i*f_j minus its diagonal sum near a confident shared label. Set u_i=pi_i0/L and s_ik=pi_ik*phi_sigma(r_ik). Construct positive exclusive prefix/suffix sums of s_j, then

```
off_diagonal = u_i*f_j
               + sum_k s_ik*(u_j + prefix_j[k] + suffix_j[k+1])
F_rho = off_diagonal + sum_k pi_ik*pi_jk*phi_rho(r_ik,r_jk)
```

This is O(K), has no subtraction cancellation, and can use log-sum-exp for very small positive terms. It marginalizes all labels without a K-by-K allocation or hard assignment.

### Circular density caveat

The mathematically normalized toroidal density is the sum over both winding integers:

```
wrapped_phi_rho(r_i,r_j) = sum_m sum_n phi_rho(r_i+m*L,r_j+n*L)
```

At zero correlation the sum factors into wrapped univariate densities. Selecting one Mahalanobis-minimizing winding is not a normalized substitute. With ordinary sigma 125 Hz versus L approximately 227,273 Hz, non-nearest images cannot contribute above the clutter floor in the existing float64 singleton implementation. The corresponding bivariate approximation needs its own proof/tests; singleton equivalence alone does not prove correlated equivalence. Exact zero-correlation score uses each wrapped component's density-weighted mean standardized winding residual. The supplied score primitive accepts those standardized means; using nearest residuals is an explicitly qualified narrow-density approximation, not a mathematical normalization claim.

## Pairing from public acquisition support

[prepare_position_windows](../../src/leo/application/regional_position_inputs.py) stores unique source-group window IDs and chosen candidate IDs. PositionObservations retains times/RX/channel, but drops support intervals. The public [project_scanner_candidates](../../src/leo/application/scanner_trajectory.py) supplies the chosen candidate's visit/probe, source sample start/end, and support start/centre/end UTC. Match prepared candidate IDs and window IDs exactly. Qualified device-counter/sample-rate authority supplies support timing; no IQ or reference coordinates are needed to recover these metadata.

The scanner projection rejects overlapping probe starts within a visit/RX. That does not independently establish cross-visit nonoverlap. Source sample offsets must retain their capture/stream/visit authority; local offsets alone cannot identify repeated samples across unrelated files. Bounding support intervals conservatively prove disjoint pilot support, whose exact sparse intervals were audited in [iteration 118](../2026_10_09_position_error_iter118/INTEGRATION_SUPPORT.md).

Fix pairing before likelihood evaluation: within exact RX/channel/actual-RF/edge identity sort by support centre then window ID; greedily pair chronological neighbours only when their positive gap is at most 2 seconds. Opposite edges or different RF centres never pair even when channel IDs agree. Each row belongs to at most one pair. Require known acquisition support and nonoverlapping bounding intervals. Repeated acquisition identities and known overlapping support remain ordinary unpaired rows, with explicit reason counts. Never pair by satellite assignment, residual size, GLRT margin or reference error. Pair eligibility may be conservative; this is not an analysis-quality filter or exclusion from dataset coverage.

The pure prototype additionally flags intervals overlapping any other row on the same receiver, not just their potential pair. Its canonical acquisition identity must bind capture/stream generation, receiver, and actual support start/end device sample counters. A visit ID alone is invalid: disjoint probe windows within one visit must have distinct acquisition identities. Local payload offsets need their immutable stream/visit authority to derive physical counters. Missing support, repeats and overlaps remain counted unpaired. No recording support adapter has run yet.

## First screen: the score at rho=0

Let R_ik be the ordinary soft satellite responsibility; clutter has zero contribution. For independent narrow Gaussian emissions,

```
S_ij = d log(F_rho)/d rho at rho=0
     = sum_k R_ik*R_jk*z_ik*z_jk
shared_label_mass_ij = sum_k R_ik*R_jk
```

Use winding-averaged z for the exact wrapped version. No posterior maximum label is selected. Report pair score and shared-label mass by recording/RX/channel/RF/edge, and by fixed alternating disjoint-pair blocks. Keep all recording members, all unpaired rows, both c arms, acquisition failures and pairing reason counts. Do not fit rho, choose a value from these scores, or evaluate geographic accuracy during this screen. Zero shared-label mass means negligible information about this particular correlation mechanism.

A separately reviewed recorded audit could use the same 12 consumed clean reconstruction members, with exact ordinary endpoint parity first. Synthetic qualification must precede it: zero-score/known positive covariance, rho derivative finite differences, uncertain labels and clutter, circular branch handling, prefix/suffix cancellation extremes, duplicate/overlap handling and exact full row accounting. The present prototype covers the score/pairing algebra only; it does not yet implement or qualify a correlated position objective.

## Identifiability and what the audit cannot show

For known labels, correctly specified Gaussian means and many independent pairs, covariance and mean parameters are identifiable in population. Those conditions are not established here. Receiver clocks, satellite timing/slopes and c were fitted using the full recording; their residuals can absorb slow covariance or retain deterministic mean error. Mixture assignments introduce further dependence, and conditioning on passing GLRT detections changes the error population. The fixed 125 Hz scale also differs from the conditional residual RMS near 62 Hz. A positive score is not an unbiased hardware covariance estimate or a calibrated independence test after full-data nuisance fitting.

For two similar spatial Jacobians, positive correlation discounts their common mode by 1/(1+rho) and emphasizes their difference by 1/(1-rho). It supplies no new position information and cannot remove a persistent spatial bias directly. It might help if B7 overcounts genuinely correlated acquisition errors; it might harm if it discounts reliable common Doppler evidence or substitutes for a deficient clock/mean model. The negative density/persistence experiments make localization gain uncertain.

The first falsifiable question is whether the soft zero-correlation score survives exact support disjointness and appears consistently in predefined blocks and both arms. A signal confined to c=0, uncertain acquisition reuse, or one recording does not justify a correlated likelihood. Out-of-block nuisance prediction would be needed to calibrate covariance after this screen; no extra optimizer is proposed now. A later matched position experiment would require a new fixed policy/protocol and separately reported frequency fit and geographic error. No rho sweep, per-scan tuning, reserve access or deployment change is authorized by this preparation.

Eight pure synthetic tests pass using the production Python environment. They cover acquisition-only chronological ordering/full accounting, repeats and cross-channel overlap, missing support, gap boundaries, exact RF/edge separation, soft score/clutter, a finite-difference covariance derivative, known zero/positive products, pair exchange symmetry and invalid responsibilities/reused indices. These tests do not qualify a recorded support join, wrapped bivariate implementation, or correlated optimizer. No recording data was loaded.

The prepared `audit_core.py` checks both saved ordinary endpoint objectives and
computes the soft score without fitting. It fixes pairing before evaluating
either arm, preserves all unpaired rows, and reports predetermined alternating
pair blocks within each RX/channel/RF/edge group. It accepts only the unchanged
125 Hz frequency scale. Three additional synthetic tests cover endpoint/order
admission, both arms and fixed block accounting, and agreement with three-image
wrapped weighted moments at alias seams. The latter qualifies the zero-correlation
score at this narrow scale, not a finite-correlation bivariate likelihood.

For 125 Hz and the 227,272.727 Hz period, every omitted nearest-image alternative
has standardized distance at least 909.09. Its Gaussian exponential is below
`exp(-413000)`, far below float64 range even after multiplying by the residual
or dividing by the fixed positive clutter floor. At a seam, individual component
winding means can differ while their contribution to the mixture score underflows.
The test compares weighted moments directly to avoid an artificial `0/0` for
such components. No physical covariance or position benefit follows from this
numerical equivalence.

Preparation amendment: the public support adapter now joins prepared candidate/window IDs to projected candidate values and their public probe metadata. Projected source sample offsets are local payload offsets, not device counters. It derives device bounds as `valid_start_counter + source_sample_bound - payload_start_sample`, subtracting integer counters before UTC conversion, and verifies the published support endpoints. Capture, raw authority, radio, stream generation, receiver, sample rate and device bounds define acquisition identity; disjoint windows in one visit remain distinct. Original observation order/fields and prepared window evidence are verified without reference fields. Missing selected candidates or probe authority retain every row with explicit unavailable support. Pairing checks unavailable support before requiring RF/edge, so an unknown edge is never fabricated and cannot remove the member. Available support still requires exact RF/edge identity. Synthetic integrated adapter/pairing coverage qualifies this preparation amendment; no recording projection or model call has run.
