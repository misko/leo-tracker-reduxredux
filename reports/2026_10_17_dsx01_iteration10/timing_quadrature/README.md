# Few timing nodes are not an accurate continuous-timing marginal

The fixed27-case qualifier completed in **0.4512s**, with no localization objectives, predictors, orbit propagation, fits, measured-CFO reads, original-state reads or station-reference reads. **Even1,025 Gauss–Hermite nodes miss the descriptive.001nat accuracy marker in9/27 cases.** No node order was changed or selected after these results. This rejects assuming that a small normalized finite-state timing grid accurately represents the continuous2s prior; it does not establish which approximation is adequate for actual RF data.

The prespecified [protocol](PROTOCOL.md) and [source freeze](source_freeze.json) precede results. [results.json](results.json) and [all-log-errors.csv](all-log-errors.csv) retain all27×6=162 signed and absolute log-density errors, including adverse cases. Four hardware-free component tests passed in0.003s before the source freeze.

## Exact oracle and every declared order

Each episode has m∈{1,4,24} rows, noise sigma125Hz, slope g∈{20,200,2000}Hz/s and residual r_i=g*delta_true with delta_true∈{0,.8,1.6}s. There is one shared delta~N(0,2²)s. The exact marginal is N(0,125²I+4ggᵀ), computed by the determinant lemma and a stable orthogonal quadratic decomposition. It is unwrapped, linear and has no visibility or point clutter; these qualifications make it an integration oracle, not a localization model.

| GH order | Cases within.001nat /27 | Worst absolute log error, nat | Worst-case m / slope / true delta |
|---:|---:|---:|---|
| 3 | 3 | 7859.350695 | 24 /2000Hz/s /1.6s |
| 5 | 6 | 3789.686878 | 24 /2000Hz/s /1.6s |
| 17 | 9 | 1517.520354 | 24 /2000Hz/s /.8s |
| 65 | 12 | 3.496506 | 24 /2000Hz/s /1.6s |
| 257 | 15 | 2.505064 | 24 /2000Hz/s /0s |
| 1025 | 18 | 1.814107 | 24 /2000Hz/s /0s |

At m24/g2000, the approximate coherent timing width is.012758s. The1,025-node log error is+1.8141nat at delta_true0,+1.1100 at.8s and−.9967 at1.6s. An order can overestimate a peak that lands near a node and underestimate one between nodes; monotonic convergence at one favorable timing is not a general accuracy certificate.

Every rule has normalized mean approximately zero and timing variance4 to floating-point precision. The1,025-order SciPy rule represents733 positive weights and292 zero weights from tail underflow; their counts are retained, rather than pretending all weights remain positive. Accurate prior normalization/moments do not prevent these narrow-likelihood errors. All rules were generated once with `scipy.special.roots_hermitenorm`; no unstable rule was silently replaced.

## Conservative bound from the saved metadata bank

The qualifier checked **1,155,960 stored interpolation cells** from all845 frozen candidates, using only their P/V arrays, times, frozen RF maximum12,459,687,500Hz and prior altitude0m. No propagation or physical predictor was called. Each cell's exact minimum interpolated position norm minus the maximum WGS84 surface norm gives a positive lower range bound; invalid cells were0.

The [protocol](PROTOCOL.md) derives the triangle/Cauchy bound

```text
|dCFO/dtau| <= RFmax/c * [||V'|| + ||P'||*max(||V0||,||V1||)/r_min].
```

Per-candidate maxima have minimum/median/p90/maximum **4316.07 /5210.99 /5860.80 /10489.35Hz/s**. Every per-candidate result is saved. These are conservative **upper bounds**, not measured Doppler slopes, lower bounds, typical rates, true-orbit error bounds, visibility-derivative bounds or timing-posterior widths. The global10489.35Hz/s bound applies to the stored linear interpolator and any permitted surface-site point, including one-sided cell derivatives. It must not be turned into a claim that actual emissions attain that slope.

## Memory is a separate barrier

The bank arrays use52.95MiB. Frozen metadata gives3988 rows and845 eligible IDs; the separately checked blocked-TRAIN subset has45 IDs, leaving800 unsupported IDs. A state(satellite,timing-node) model with one clutter state has D=46+800*order. Exact formula costs are:

| Order | D states | One float64 N×D plane, MiB |
|---:|---:|---:|
| 3 | 2446 | 74.42 |
| 5 | 4046 | 123.10 |
| 17 | 13646 | 415.19 |
| 65 | 52046 | 1583.55 |
| 257 | 205646 | 6256.99 |
| 1025 | 820046 | 24950.74 |

This is one plane only: emissions, forward/backward arrays, geometry derivatives and optimizer state can require more. A streamed forward vector is smaller, and checkpointing can reduce stored arrays, but neither removes the emission/gradient work. These formulas are not measured optimizer RSS or throughput. This qualifier stops without a denser grid, a prior shrinkage, a delta-zero replacement or a real-data fit.

## Tractable alternative to review

A metadata-only microepisode of at most four observations permits an analytic **linear-timing working model**. If r_n(delta)=r_n(0)−g_n*delta and visibility/point-signal weights are frozen with respect to delta, expanding point-clutter choices gives at most2⁴=16 signal subsets. Each nonempty subset integrates exactly to a rank-one Gaussian marginal like this oracle; the empty subset is uniform clutter. One shared2s Gaussian is integrated per episode, rather than fitting hundreds of timing coordinates or discretizing each into thousands of states.

For a population branch, a declared mixture of the original identified point-product and a normalized catalogue-weighted microepisode marginal can preserve the identified baseline exactly at zero birth mass. Episode membership must use only lane/time metadata, and timing is explicitly episode-specific. It can mix emitters; clutter is an alternative, not proof that four observations share an emitter.

This is **not an exact orbital model**. At a2s prior scale, frequency curvature times delta² may matter. Finite-alias density requires consistent wrapped multivariate image sums/tail control, not an unwrapped Gaussian plus circular residual shortcut. Horizon visibility can vary with delta. Any later component must qualify alias normalization, point-clutter subset algebra, missing-emission conditioning and exact-orbit linearization/visibility error over the declared domain before fitting. No such microepisode component was implemented here.

## Tests, ledger and reproduction

[test_quadrature.py](test_quadrature.py) verifies single-row Gaussian convolution, heterogeneous multivariate-normal/determinant-lemma parity, node-weight scale/permutation invariance, and exact segment minimum/radial-derivative bound checks including invalid lower ranges. Tests use only NumPy/SciPy and synthetic arrays, without hardware or corpus requirements.

The frozen run ledger is27 analytic marginals,162 synthetic quadrature marginals,6 rules and1,155,960 metadata-cell arithmetic checks. Localization objectives, predictors, propagation and fits are all0; no station or measured-CFO input is opened. Component-test evaluations are separate from this ledger. The execution exited0 under60s TERM/65s KILL, single-threaded numerical libraries, using the pinned scientific Python runtime.

The ledger's `original_state_reads=0` refers to fitted endpoint states. The precomputed orbital P/V arrays are read explicitly for the metadata-only bound, as declared. Their float64 bound calculation is not a formally outward-rounded interval-arithmetic certificate.

From the repository root, the historical generation sequence was `qualify.py freeze`, followed by `timeout --signal=TERM --kill-after=5s 60s .../python qualify.py run` using the pinned runtime and the paths in `source_freeze.json`. Files use exclusive creation; preserve the sealed directory rather than rerunning into its output paths. No HMM/population adapter, real-data fit, parameter tuning or RF campaign follows this accuracy/cost result.
