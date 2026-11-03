# Conservative shared-curvature localization prototype

Nine inherited eight-scan DS7/DS8/DS9 panels. Freeze one prior width:
0.1 canonical Hz/s², zero-mean Gaussian truncated and normalized at ±6 sigma.
It is a conservative engineering choice, not calibrated orbit uncertainty.
Do not tune it from reference errors or held scores. Initialize at each
existing cached q020 fit; this is a local prototype, not a multistart search.

Construct each track's quadratic time basis by projecting time squared against
intercept and linear time on training samples only. Hold that basis fixed for
training and full likelihood. Share a curvature coefficient by recording,
physical catalogue candidate, exact RF. Groups require both RXs, training MAP
joint signal probability >=0.5, and at least eight training samples spanning
ten seconds per member. Membership is frozen at the baseline training fit.

Only the designated candidate component receives the curvature correction.
Keep alternatives, uniform visible-candidate priors, per-track constants
eliminated by contrasts, and q020 trend background unchanged. Integrate the
product of grouped mixtures under a common latent coefficient (128 nodes),
not separate track marginals. Audit at 256 nodes. Report conditional held
log score and the original unmodified q020 held score at the new location.

Use inherited E/N ±12 km, per-scan time ±5 s, L-BFGS-B maximum100 iterations,
160 function evaluations. Qualify only optimizer success, no boundary within
0.001, maximum gradient <=0.01, derivative replay <=0.02, and all quadrature
score/held/gradient differences <=0.01. Bound nine workers individually to
180 seconds and concurrency to three. Report failed fits without replacement.

Report paired geographic errors against the inherited exposed unsurveyed
reference; no promotion based on interleaved held prediction alone. This is
not independent site/UTC/orbit validation. No new RF or production changes.
