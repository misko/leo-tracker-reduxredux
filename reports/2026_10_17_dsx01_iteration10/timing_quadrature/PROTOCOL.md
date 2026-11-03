# Shared-timing integration accuracy, before any population fit

This is a bounded numerical qualifier, not a localization objective or new fit. Freeze this protocol, code, tests and input hashes before computing the results. Read only the existing metadata-bank arrays/freeze and the old qualifier's metadata count45; do not read measured CFO, original fitted states, station configuration or IQ. No orbit propagation, RF collection, model fitting or production change occurs. Whole compute command is capped externally at60s TERM/65s KILL; one worker, numerical libraries single-threaded. Stop on errors without parameter changes or a replacement campaign.

## Frozen synthetic matrix

Use residual vector r_i=g*delta_true for i=1..m, independent observation sigma125Hz, one shared latent delta~N(0,2²)s, and prediction g*delta. Evaluate every combination:

- m∈{1,4,24}
- g∈{20,200,2000}Hz/s
- delta_true∈{0,.8,1.6}s

There are27 cases. The exact marginal is the multivariate Gaussian N(0, sigma²I+4ggᵀ), evaluated by the determinant lemma and a stable orthogonal decomposition of its quadratic form. This is an unwrapped linear synthetic model, intentionally without aliasing, visibility or point clutter; those add integration complexity and cannot make this oracle a full physical-model qualification.

Compute probabilists' Gauss–Hermite nodes/weights with `scipy.special.roots_hermitenorm` at the six fixed orders3,5,17,65,257,1025. Normalize the positive represented weights, retain zero weights from floating-point underflow explicitly, and evaluate the Gaussian product mixture with logsumexp. Nodes represent delta=2*z. Report every signed/absolute log-density error against the analytic marginal, node-weight diagnostics, and results by order without dropping adverse cases. An absolute log error≤.001nat is a descriptive accuracy marker, not an authorization to select an order or approve a later model. No new order, error-based retuning, held data or delta-zero substitute follows failures.

Ledger:27 analytic marginal calls,162 synthetic quadrature marginal calls and6 generated quadrature rules. These are not localization-objective calls. Component tests separately verify scalar convolution, multivariate-normal/determinant-lemma agreement and quadrature weight-scale/permutation invariance. Record test calls separately from the frozen27-case run.

## Optional physics-only derivative bound

Inputs are the sealed845-candidate metadata-bank.npz, its freeze.json and the old actual qualifier's source_freeze.json (candidate-count metadata45 only). Require matching bank SHA and845/3988 counts, nodes and arrays. For every linearly interpolated cell P(a)=P0+a*(P1-P0), a∈[0,1], compute its exact minimum norm using the clipped quadratic minimizer. Any observer on the public fixed-height WGS84 ellipsoid satisfies ||site||≤6378.137km+|height_km|. Therefore

```text
r_min = min_a ||P(a)|| - (6378.137 + |height_km|)
|dCFO/dtau| ≤ RFmax/299792.458 *
             (||V'|| + ||P'||*max(||V0||,||V1||)/r_min)
```

P' and V' are the exact cell differences divided by its time step. The inequality follows by differentiating radial velocity: u'=(I-uuᵀ)P'/range and d(u·V)/dt=u'·V+u·V'. Velocity norm is bounded by the larger endpoint norm by convexity. This bound is valid everywhere within each stored cell for any permitted prior point, and at the one-sided derivatives at cell boundaries. It bounds the **stored linear interpolator**, not the true orbit between samples or ephemeris error. It does not bound horizon derivatives, curvature, posterior timing width or likelihood-integration error.

Use the RF maximum and altitude in frozen metadata, not a fitted or reference position. If any range lower bound is nonpositive, report the invalid count and omit a global bound; do not silently exclude those candidates. Persist per-candidate bound/minimum-range metadata and aggregate summaries. No propagation or predictor/objective call is permitted. The bank arithmetic is batch-limited; check the whole deadline around batches.

## Cost and interpretation

Report exact N3988, K845 and selected-count45 from frozen metadata, and arithmetic state/emission-array memory estimates for all six declared node orders. The unsupported count is800 under the separately checked subset relation; this qualifier does not rerun discovery or read selected fitted states. D=1+45+800*order includes one clutter state. Report float64 bytes for a full N×D plane and a D-vector, plus original bank-array bytes. These are formulas, not measured optimizer peak RSS or throughput.

Few normalized nodes can still miss a narrow timing likelihood. A coherent m-row episode can narrow the effective timing width to roughly sigma/(|g|*sqrt(m)); adequacy for individual rows does not establish episode marginal accuracy. No finite-state HMM normalization test proves that its discrete timing prior approximates the continuous2s Gaussian. If the slope/resolution cost is prohibitive, the next alternative to review is an explicitly approximate analytic linear-timing microepisode model with separate exact-orbit/visibility/alias-error qualification. No population/HMM adapter or real-data fit is authorized here.
