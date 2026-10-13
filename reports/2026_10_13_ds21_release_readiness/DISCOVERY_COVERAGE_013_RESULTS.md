# DS21-013 discovery coverage control

The prespecified denser grid recovers nearby discovery proposals on DS21-013.
All three training-selected centers now lie within 25 km of the configured
reference in optimizer coordinates, so their local disks include it. The
original discovery selected three centers outside that radius. This removes
the necessary local-domain exclusion demonstrated in the original DS21-013 audit;
it **does not establish final A/B/C position accuracy**. Those original severe
model results remain unchanged.

The [frozen control](DISCOVERY_COVERAGE_CONTROL_PROTOCOL.md) changes only grid
levels from `[100, 50, 25, 12.5]` to `[50, 25, 12.5]` km. It retains 100 points,
all-view priority, original training observations/partition/priors and the
same 1,052-satellite full regional bank. Point-local bootstrap unions still
vary with geography; this is not the downstream 49-satellite model pool.

| Discovery measurement | Original | Control |
| --- | ---: | ---: |
| Evaluated points | 100 | 100 |
| Points at 100 / 50 / 25 / 12.5 km spacing | 16 / 16 / 24 / 44 | 0 / 80 / 12 / 8 |
| Deferred cells at point-budget stop | 76 | 113 |
| Stored fit results, all views | 300 | 300 |
| Stationary results, all / low / high | 99 / 100 / 99 | 99 / 100 / 100 |
| Total stationary results | 298 | 299 |
| Points visited within 25 km of reference, optimizer coordinates | 0 | 9 |
| Nearest visited point, optimizer coordinates | [-50, -50] | [-81.25, -81.25] |
| Nearest visited distance, optimizer km | 48.291651 | 5.791596 |
| Terminal elapsed seconds | 368.056147 | 361.222082 |

The control's slice termination records **361.223237 seconds**, within the
480/495/500-second internal/TERM/KILL limits. All 80 initial 50 km centers fit
within the point budget, leaving 20 score-prioritized evaluations. More deferred
cells and a nearby visit do not prove exhaustive coverage, a globally optimized
score or guaranteed 25 km coverage throughout the prior.

The three selected control proposals are:

| Order / selection origin | East, north km | Candidates | Optimizer distance km | 25 km disk slack, optimizer km | Saved geodesic error km |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 / low-view minimum | -93.75, -81.25 | 20 | 6.719203 | 18.280797 | 6.719037 |
| 1 / all-score fallback | -87.5, -62.5 | 21 | 18.496686 | 6.503314 | 18.496084 |
| 2 / all-score fallback | -81.25, -93.75 | 25 | 14.009678 | 10.990322 | 14.008947 |

These centers differ from the nearest visited point. Selection uses the original
low/high/all ranking, then separated all-score candidates, with 12.5 km minimum
separation. The high-view minimum at `[-87.5, -87.5]` is only 8.838835 km from
the first selected center and is excluded by that unchanged separation rule.
The all-view minimum coincides with the first center. Consequently the second
and third proposals are all-score fallbacks, not independently selected high/all
minima. No reference distance selected or reordered a proposal.

Original selected-center optimizer distances are 258.454921 / 199.205255 /
182.457260 km. The control's optimizer distances and disk slacks use the already
audited DS21-013 inverse reference point; its geodesic errors above are copied from
the sealed evaluator, not recomputed. These two distance definitions are
distinct. All geometry is a post-seal diagnostic against a configured reference,
not an independently surveyed location or new final model estimate.

Training-score effects are separate:

| View | Original stationary minimum | Control stationary minimum | Original median | Control median |
| --- | ---: | ---: | ---: | ---: |
| All | 33906.372619 | 31241.270693 | 37413.822199 | 37846.124409 |
| Low | 17621.536717 | 16624.688772 | 19183.921110 | 19469.878017 |
| High | 15688.960323 | 14530.797120 | 17041.791466 | 17295.377017 |

The minima improve while the medians increase over the differently allocated
point samples. Each score is its own view's fitted training objective, including
priors. Candidate unions can differ between points, so these discovery scores
do not prove improvement under one common-support objective. Different views'
scores are not interchangeable, and lower frequency loss is not position
confidence. Selected objective/NLL/prior-gap/RMS ledgers remain in the JSON.

Twenty geographical points occur in both runs. All 20 have identical candidate
unions, and all 60 shared-point fit vectors/nuisance arrays, objectives, NLLs and
KKT values match exactly. This supports unchanged common-point math, without
asserting comparable candidate subsets at different geographies. All 100 control
points were freshly evaluated in the separate namespace; failed calls were not
retried within either namespace.

The control retains one nonstationary all-view fit at `[125, 175]`, with KKT
**0.001721963**, above the unchanged 0.001 threshold despite solver success.
The identical failure is present in the original run. Its other retained
high-view failure at `[206.25, 118.75]`, KKT 0.698604120, is not among the control's
visited points; the change from 298 to 299 stationary fits is not evidence that
this failure was repaired. Neither run has missing fit slots or recorded
bootstrap/projection/fit exception strings. Where such strings occur, the
point schema does not identify every failure stage separately; missing fits
must not be inferred as completed optimizer calls.

The [independent receipt audit](DISCOVERY_COVERAGE_013_AUDIT.json) verifies
1,835 distinct file hashes, 404 control live/archive sources, the unchanged 402
original source entries and full bank, 200 point receipt/launch/termination
triplets, both hierarchy replays and both training selectors. Original preparation
hashes, randomized partition, clock nodes, prior and causal TLE snapshot match.
There are zero new optimizer, likelihood or orbit calls in the audit. Reference
functions were not called; optimizer-plane arithmetic used the existing DS21-013
post-seal coverage ledger. Root's independent count/geometry/common-point replay
agrees. The control terminal SHA-256 is
`ef9dd970eea040f02af2736a2b21fd8e8902cd9f4dcf6d9e2b3120076f84b520`.

The runner is commit `d373e9e47`; its 19-case suite and two targeted checks
passed, 20 cases collect, and Ruff passed. All new fits use fitted c, original
five-second bootstrap budgets and five-second/200-iteration fixed-position
fits, with one science process and one BLAS thread. Held observations and locked
cases were not used. Source, point, slice, hierarchy and selection seals precede
the reference join.

This coverage recovery warrants qualification of a new downstream parent
adapter under the unchanged shape/bootstrap/hybrid/model science. No downstream
comparison has yet run from these proposals. The original DS21-013 baseline is
preserved; the full-DS21 0.5 km target remains unmet, and DS21-025 remains
metadata-ready without a freeze or initialization run.
