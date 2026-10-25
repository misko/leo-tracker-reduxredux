# RF-only nonlinear new-family uncertainty diagnostic

The matched experiment supports a specific mechanism in DS24-0095: setting the
recovered family's three physical shape modes to zero variance creates a much
stronger position pull than retaining their declared engineering-prior
covariance. The two fitted endpoints differ by 1.016 km with c=0 and 1.246 km
with fitted c. DS24-0087 changes by only 2.19 m and 1.69 m. These are RF-derived
endpoint differences, **not geographic accuracy results**.

All 88 fixed-position comparisons and eight predeclared fits completed. Every
fit passed the original parent validity, ID preservation and independent-rule
endpoint numerical checks. The new sources remain **unqualified experimental
predictive factors**, with zero newly accepted target associations. The saved
baseline remains operational. This two-case development diagnostic does not
establish correct satellite identity, calibrated orbit uncertainty, or a general
recovery policy.

## Matched evidence and information flow

The exact sealed additions are 49 RX1 CH5 observations modeled as NORAD65500 in
DS24-0095 and 43 RX2 CH7 observations modeled as NORAD57752 in DS24-0087. There
was no new catalogue search, identity change, point trimming, RF collection or
IQ access. Observations, aliases, parent state construction, source constants,
unseen-noise convention, regional start and optimization budgets match between
`predictive_shape_zero` and `predictive_shape_prior` and between c arms.

Neither source enters curved calibration or the Gamma/noise learner. At a fixed
position, target CFO redaction leaves parent coefficients, phase references and
Gamma precision unchanged. Target evidence can influence position, which in
turn changes the parent geometric calculation. Original predictive evidence E
and the new source T share the parent curved posterior C through the exact
conditional construction

    p(E,T|C,x) = p(E|C,x) integral p(T|E,C,x,phi) p(phi|domain) dphi.

The E/T shared receiver covariance is retained. Dormant parent-family phase and
shape slots are zero in the target shared design; its phase and optional shape
uncertainties are target-local and counted once. Shape is integrated through
the original three physical mode columns at scale one, evaluated at each phase
node. The branches differ only in this shape covariance.

Parent curved/predictive likelihood counts remain 2262/0 for DS24-0095 and
2957/644 for DS24-0087. The new 49/43 experimental predictive inputs bring the
experimental position-likelihood totals to 2311/3644. They do not increase
accepted associations or active curved-calibration ownership. The frozen
operational baseline compatible counts remain 2671/4050 and 3601/4401.

## Phase approximation and domain

The rejected first preparation linearized target phase at its causal mean.
Independent direct propagation found 115–129 Hz of nonlinear error in 0095 at
one original prior SD, after removing constant and tangent-phase components;
the deleted shape prior projects to about 34 Hz. For 0087 these quantities are
about 1.42 Hz and 0.86 Hz. No position fit used that rejected approximation.
This does not diagnose the same error in the original baseline, which refreshes
its local phase references.

Amendment02 integrates direct propagated Doppler under the original causal
Student nu=3 distribution **conditioned on [-15,+15] seconds**, without
recentering or shrinking. This is an explicit domain-conditioned prior.

| Case | Original location / marginal SD (s) | Removed prior mass | Conditional mean / SD (s) |
| --- | --- | ---: | --- |
| 0095 | -2.296774 / 6.282140 | 2.846380% | -2.132187 / 4.567776 |
| 0087 | -0.359190 / 0.732391 | 0.004943% | -0.359137 / 0.709302 |

All density normalization terms are retained. Phase posterior moments are
diagnostic inference under marginalization, not a new optimized calibration
coordinate. No endpoint has nonzero numerical posterior mass beyond |phi|>14s;
this observation does not remove the explicit prior-domain limitation.

## RF movement and complete score decomposition

The following differences compare each new endpoint with the saved baseline
endpoint, using east/north coordinates only and no geographic reference.

| Case | c arm | Zero-shape shift (km) | Prior-shape shift (km) | Zero/prior separation (km) |
| --- | --- | ---: | ---: | ---: |
| 0095 | c=0 | 1.243468 | 0.229258 | 1.016088 |
| 0095 | fitted c | 1.344861 | 0.099251 | 1.245680 |
| 0087 | c=0 | 0.107254 | 0.107876 | 0.002187 |
| 0087 | fitted c | 0.125857 | 0.126617 | 0.001687 |

At the saved 0095 fitted-c baseline versus old phase-only-support positions,
with the same saved parent phase reference and full likelihood mask, the parent
objective worsens by 1.644735. The zero-shape target improves by 4.219853,
preferring the support direction despite the parent cost; total change is
-2.575118. With shape-prior covariance, target improvement is only 0.175000 and
the total change is +1.469735, reversing that endpoint preference.

The target change is dominated by expected Gaussian quadratic energy:
-4.215475 with zero shape versus -0.171457 with prior shape. Expected logdet
changes are +0.004183/-0.001971, phase posterior/prior quadrature penalties
-0.008561/-0.001572, and density normalization is unchanged along the segment.
This is the full phase mixture, including posterior reweighting; an RMS change
alone would not explain it. The c=0 total changes show the same reversal,
-2.220534 versus +0.791750. In 0087 the matched endpoint preference changes
little between covariance branches.

At their own new fitted endpoints, prior-shape minus zero-shape full RF
objective is -6.592208/-11.628423 for 0095 c=0/fitted c, and
+0.000750/+0.005020 for 0087. These normalized frequency-evidence scores remain
separate from geographic accuracy.

## Qualification, numerical bounds and runtime

One common 1281-node phase-space Gauss-Legendre rule was frozen before scientific
propagation. All 160 preparation probes checked both branches at baseline,
support, midpoint and cold regional start plus axis offsets. The largest score
discrepancy from independent adaptive integration was 6.0784e-5; largest
central-difference gradient discrepancy was 1.1298e-4 objective/km at h=.01 km.
Both pass the predeclared 1e-3 limits and a strictly denser 2561-node check.
Prior numerical mass error is at most 2.043e-13. Preparation took
137.536677665 s; code-writing time is not numerical runtime.

Every final endpoint was checked again with its actual final parent phase
reference, at the endpoint and +/- .01 km on each axis. The maximum score and
gradient discrepancies from adaptive integration were 1.86797e-5 and
3.22993e-5 objective/km. There was no endpoint refinement or retry. All tested
phase nodes and domain endpoints were visible; invalid propagation would have
failed the arm rather than dropping nodes.

The eight fits took 17.985–25.966 s each, including endpoint qualification,
within 180 s per arm. Summed fit-worker time was 170.327821943 s; total run wall
time including profiles and process startup was 100.698457805 s, within the
1200 s global cap. Two workers each used one BLAS/OMP/MKL thread. There were no
timeouts, failures, multistarts or constrained rescues.

Original `r.valid` predicates check compatible nonempty parent tracks,
predictive gates, endpoint finiteness and region, final phase convergence, and
unclipped posterior phase bounded by 15.000001 s. Gamma convergence and original
accepted/likelihood ID preservation are also checked. All eight fits and all
four matched c-arm conjunctions pass. No calibrated acceptance gate exists for
the new experimental target, so passing parent/numerical checks is not target
association acceptance.

The complete normalized target mixture NLL is appended once as one scalar
square-root residual. Its scalar objective matches the reported score up to
the original fixed parent normalization/noise offset. This representation has
different Gauss-Newton curvature from separate Gaussian observation factors;
the same bounded five-round, 48-iteration ordinary solver is an approximate
optimizer of that exact scalar. It is not a global-optimality claim.

## Preserved preparation corrections

Preparation01 remains preserved with zero fits: its first-order phase
approximation failed the physical adequacy check. Independent construction
audit also caught mutable cached-parent dictionary accumulation before freeze;
the prepared adapter uses a fresh dictionary and repeated-position regression
tests verify the original parent is unchanged.

The first nonlinear execution freeze02 also has zero scientific profiles/fits.
Independent preflight found missing original absolute-phase/endpoint/nonempty
qualification predicates and unenforced top-level file hashes. Separately
versioned execution03 reuses exact original validity predicates and enforces
all declared file hashes. Seven targeted tests pass, including four real
baseline contexts, hidden phase-bound violations and hash-mismatch rejection.
No likelihood or quadrature changed, so the numerical preparation was retained.

## Artifacts and limits

- Frozen execution: `protocol03.json`, `execution03.py`, `quadrature02.py`.
- Inputs and deleted-prior projections: `preparation01/input_bindings.json` and
  `preparation01/deleted_prior_projections.json`.
- Numerical selection: `preparation02/protocol.json`, `result.json`, `points/`.
- All 88 profile exports: `profiles03/`; every fit round, raw endpoint,
  qualification, gate ledger and RF diagnostics: `fits03/`.
- Primary RF seal: `RF_seal03.json`, SHA256
  `642c438662bdb23503ce6aa1cc9adc33f6a0394ec8b0aa7c49fc5b95f73e7142`.
- Read-only derived table: `RF_summary03.json` and `RF_summary03_seal.json`.

The saved ordinary full-shape graph controls remain invalid under their original
owner-support rule. Restoring uncertainty as a predictive factor does not make
those graph trials valid by renaming them. Comparisons to saved graph/phase-only
controls also change evidence role and phase treatment; only the two new
branches isolate shape covariance.

The two scans are already examined development cases with prior geographic
exposure, not an unseen validation sample. The experiment supports a model
mechanism, not measured physical orbit error or externally verified identity.
Geographic evaluation belongs to the independent reviewer after this RF seal.
No ALGO promotion, broader cohort or general new-family retention policy follows
automatically from these two results.
