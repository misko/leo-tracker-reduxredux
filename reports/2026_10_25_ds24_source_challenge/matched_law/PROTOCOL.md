# Six exogenous-background same-law controls

Use the two archived source layouts DS24-0010/0011 from the earlier conditional
nomination study. Native times, RF, IDs, causal catalogue and common saved c0 RF
coordinate are fixed. No original CFO array or dataset is changed. These are
inherited response-selected layouts, not independent end-to-end GLRT controls.

Freeze one exogenous radio Gaussian mean/covariance per arm before any new CFO
draw. Reconstruct the original full-parent conditioning, without removing any
candidate family and without using synthetic responses. Every candidate/null
uses that same background. This is a conditional exogenous model, not the true
shared-family hierarchical law when a tested label also occurs in the parent.
The Gaussian noise law includes the original unseen-Gamma second-moment
surrogate and independent 300 Hz owner constant once.

Six vectors total: two physical and one near-null per layout. Generate under
c0 only. c0 is the exact matching-law control; fitted-c scores THE SAME vectors
with its own frozen background and is explicitly an off-law sensitivity.

Select one response-free pair per layout from causal labels absent the original
parent and certified fully nominally visible throughout [-15,+15] s. At causal
means, minimize delta' [C0 + .5(sd_a² d_a d_a' + sd_b² d_b d_b')]^-1 delta,
delta=f_a-f_b, at the same canonical alias0. All quantities are native-q-scaled;
NORAD-sorted pair order breaks ties. This is an affine Gaussian design metric,
not the exact Student/alias mixture distance. No data draw enters selection.

Physical generation and exact scoring use original causal Student nu3 with
scale=original marginal SD/sqrt3, conditioned on [-15,+15], exact nonlinear
nominal Doppler/full B(phi), unit Gaussian shape coefficients, the same fixed
background covariance and uniform whole-source aliases -4..4. Generator labels
have certified full nominal support. For other scored labels, invisible phase
likelihood is zero with the original operational-domain normalizer retained;
never condition again on a label's visible mass. Visibility here concerns the
nominal bank, not detection probability integrated over physical modes.

The close null is a proper Gaussian polynomial perturbation around the physical
pair midpoint. Q is an orthonormal degree4 native-time Legendre basis. Its
coefficient covariance is Q'SQ + (n/5)*median(native_sigma)^2 I, with S the local
affine phase/shape prior design covariance of the pair plus their between-mean
spread. Phase variances in S are from the original conditioned prior. This is
NOT exact nonlinear physical moment matching. The added covariance gives
expected total roughness n*sigma² in the original point space. Freeze mean,
basis and coefficient covariance before draws; use those exact arrays in null
generation and normalized finite-alias score. It is not empirical clutter.

Seeds: independent PCG64 children of SeedSequence([2026102551, case_integer,
trial0..2]) for phase, shape/polynomial, Gaussian noise and alias. No redraw.
Archive every latent, Gaussian normal and synthetic CFO vector.

The unchanged ordinary full-catalogue coarse screen sees only raw observations,
fixed covariance and catalogue; it never receives truth/type/pair labels. Its
approximate affine phase and unrestricted integer alias are tested as-is;
report outside-law proposals without clipping. Freeze c0 top8 for exact scores
in BOTH arms. Fitted-c's separate ordinary screen is diagnostic only. If truth
is absent, score it separately as a label-available diagnostic; never backfill
or reinterpret the ordinary shortlist. Compare ordinary versus available-label
sets under identical priors/background, with an explicit unresolved model.

Reuse existing normalized visibility support, log integration, physical
enclosures and early dominated-candidate bounds. Preserve every failure and
unscored slot. Distinguish finite-pool ordering, absolute precision and identity
acceptance. There is no operational identity acceptance rule here.

Actual context smoke, owned tests and source/input freeze precede B preflight.
At most 600 cumulative numerical worker seconds including preparation/tests,
two case workers/one BLAS thread each. Within each case, score all c0 trials
before fitted-c sensitivities. No scientific retry, budget extension, position
fit, GPS, RF/IQ processing or parameter tuning follows results.
