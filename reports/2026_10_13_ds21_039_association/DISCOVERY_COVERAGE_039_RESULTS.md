# DS21-039 qualified discovery coverage result

The unchanged coverage policy completed **100 points and 300 fitted-c discovery
fits, with 296 stationary**, in its first 337.358-second slice. The three
training-selected points have saved postseal errors of **26.283, 306.219 and
38.433 km**. These are fixed-geography discovery proposals, not final A/B/C
localization results. No algorithm or downstream candidate is promoted.

The important selection effect is specific: the new high/all stationary minimum
at **[-106.25, -93.75] km** lies only **8.839 km** from the low winner
[-112.5, -87.5]. The original low-first selector therefore skips that minimum
under its unchanged 12.5 km separation rule. The distant second proposal
[-75, 225] is an **all-score fallback**, not the high-band minimum.

| Proposal | Historical selected center km | Control selected center km | Control ranking origin | Saved control error km |
| --- | --- | --- | --- | ---: |
| 0 | [-81.25, -106.25] | [-112.5, -87.5] | Low minimum | 26.282622 |
| 1 | [-6.25, -131.25] | [-75, 225] | All-score fallback | 306.218647 |
| 2 | [-25, -125] | [-125, -75] | All-score fallback | 38.432603 |

All selections precede the reference join. No historical proposal errors were
recalculated for this comparison. Saved geodesic errors are not distances in
the optimizer's geographic chart; this report makes no claim that a particular
25 km optimizer disk excludes the reference.

## Matched search and numerical controls

| Receipt measure | Historical discovery | Coverage control |
| --- | ---: | ---: |
| Points at 100 / 50 / 25 / 12.5 km spacing | 16 / 22 / 26 / 36 | 0 / 80 / 12 / 8 |
| Stored fits: all / low / high | 100 / 100 / 100 | 100 / 100 / 100 |
| Stationary: all / low / high | 97 / 99 / 100 | 99 / 98 / 99 |
| Deferred cells at point-budget stop | 75 | 119 |
| Selected discovery candidate union | 35 | 39 |

Both searches use the identical 836-satellite regional bank, original causal TLE
snapshot, 250 km prior, all/low/high training inputs and fitted-c numerical ports.
The intervention spends 80 points on the original aligned 50 km initial lattice,
leaving 20 for refinement, rather than starting at 100 km. Budgets remain
100 points, 5 seconds per bootstrap, 5 seconds/200 iterations per view fit, with
the original candidate-union and calibration rules. The slice cap remains
480/495/500 seconds internal/TERM/KILL; no continuation or numerical retry was
needed. The four nonstationary control outcomes are retained and excluded:
low [75, 25] and [-93.75, 231.25], all [125, -175], and high [-125, -25]. There
are no recorded fit exceptions. The four historical nonstationary outcomes also
remain unchanged.

The searches share **27 points**. Their catalogue unions agree at every shared
point, and all **81** corresponding fitted vectors, nuisance arrays, objectives
and likelihood NLLs are **exactly equal**, with maximum saved deltas zero. This
checks the numerical comparison on common support without rerunning any fit.
It does not establish candidate emitter identities or global search optimality.

| View | Historical stationary minimum center km | Control stationary minimum center km | Historical objective | Control objective |
| --- | --- | --- | ---: | ---: |
| All | [-81.25, -106.25] | [-106.25, -93.75] | 35139.658875 | 34593.563198 |
| Low | [-81.25, -106.25] | [-112.5, -87.5] | 21540.390829 | 20900.012205 |
| High | [-6.25, -131.25] | [-106.25, -93.75] | 14299.514748 | 13085.389386 |

These lower discovered objectives do not establish better localization or a
global likelihood improvement: point-local candidate sets differ. The old/new
selected discovery unions share 19 catalogue numbers, adding 20 and omitting 16.
Their sizes, 35 and 39, are distinct from the historical **43-satellite final
model pool**, which includes later initialization expansion. No new shape,
bootstrap/hybrid proposal chain or A/B/C fits have been run from this control.

## Authority and limits

The [prespecified protocol](DISCOVERY_COVERAGE_039_PROTOCOL.md) qualifies genuine
legacy receipts without relabeling them as generic initialization authority.
The separate training qualification completed in 19.602 seconds under its
60-second internal cap and bound the original prepared evidence, partition and
training frames. Training contains 2,798 / 1,692 / 1,106 windows; seed 20261012,
20-second counter groups and held labels 2, 6 and 12 are unchanged. Held data
were not prepared or used. All **406 live/archive source hashes**, the historical
source/input/bank authority, qualification/runtime bindings, numbered slice,
100 point launch/result/termination triplets, hierarchy and selector pass the
[independent receipt audit](DISCOVERY_COVERAGE_039_AUDIT.json).

The initial metadata pin failed because two authority-map keys used relative
input/census paths while validation rebound them to absolute paths. That failed
pin remains untouched. The successful `discovery-coverage-v1-absolute-source`
namespace uses absolute paths with identical source bytes and policy; all
authority values match after path normalization. No qualification, preparation
or numerical attempt began in the failed namespace. This operational correction
is not a numerical retry; the frozen adapter's relative-path limitation remains
documented. Historical discovery lacks a complete transitive source archive and
modern numbered receipts; those missing attestations were not invented.

Terminal SHA-256 is
`446c82c25cfa691cafe3986a0bf5d97bc50cd74810f23dace1d52803a63d5b78`;
postseal evaluation SHA-256 is
`228cc88f93dd6425b9ff8d88056e7c0725a05fc5d65fa56a76ea8a038c66cc70`.
The audit reads saved metadata and performs arithmetic only, with no new
preparation, prediction, objective, optimization or reference evaluation.

The smallest next discriminating control is a training-only comparison of
**all-first versus original low-first selection on these same 100 saved points**,
retaining the 12.5 km separation and candidate-pool rules. That would isolate
the observed ordering/separation effect without another grid or fit budget.
Its exact protocol and any downstream authority adapters remain separate work;
no reference-based point substitution or automatic budget expansion is justified
by this result. Discovery alone has not achieved the full-DS21 sub-0.5 km target.
