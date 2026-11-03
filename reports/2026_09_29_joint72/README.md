# One joint position across 72 DS7/DS8/DS9 source scans

This bounded experiment combines the existing three N24 source pools using
the unchanged q020 model: one shared geographic location and 72 per-scan
timing offsets. It assumes the physical receiver location was unchanged
across datasets. That is a modeling assumption inherited from the common
reference analyses, not independently verified stationarity.

**Decision: retain the separate dataset fits.** The single joint estimate is
244.79 m from the inherited reference; the unoptimized mean is 233.28 m away.
Neither improves outside-scan prediction over the existing per-dataset N24
positions overall. Both remain substantially worse than the N8 location
mixtures on these targets. More pooling alone does not resolve the observed
predictive mismatch.

| Target dataset | Joint vs its N24 fit | Mean vs its N24 fit | Joint vs N8 mixture |
|---|---:|---:|---:|
| DS7 | −18.745 | −14.926 | −205.807 |
| DS8 | +4.250 | +7.219 | −143.884 |
| DS9 | −10.827 | −8.427 | −120.623 |
| Total | −25.322 | −16.134 | −470.315 |

Values are sums of predictive log-score differences across five targets per
dataset; positive favors the new position. Both joint and mean positions
beat the per-dataset baseline on only 5/15 targets. The joint position beats
the mean on 5/15 and loses −9.187 in aggregate. It beats the N8 mixture on
2/15. Geographic proximity to the exposed reference and predictive performance
are not interchangeable measures.

![Joint-position comparison](comparison.png)

The existing per-dataset N24 errors are 387.52, 389.83 and 107.23 m. The joint
245 m estimate should not be counted as three independent sub-km successes
or as an improvement over the strongest dataset-specific estimate. The
center-only control is about 809 m away. Independent receiver coordinates
and timing evidence were requested; none was incorporated in this run.

The result is compatible with scan/dataset-dependent model discrepancies,
but does not identify their physical cause or prove receiver motion. It
argues against forcing a single point estimate as a cure for the predictive
disagreement. Further work should distinguish calibrated uncertainty and
shared physical errors from mere gains against the inherited reference.

Two initial positions were frozen: the configured center and the arithmetic
mean of the three N24 positions in east/north coordinates. Both use each scan's
previously fitted source timing as initialization. The highest qualified
training likelihood selects the joint position. Target and reference errors
do not choose the start. The unoptimized mean is a separate simple control.

The same fifteen timestamp-selected outside-pool targets are scored at both
positions. Complete-scan q020 likelihood integrates one timing offset uniformly
over [−5,+5] s per target. No target timing, location, grouping or model width
is fitted. The old per-dataset N24 position, configured center and equal N8
location mixture remain fixed comparison arms. Their scores are sealed and
reused. A shared-position fit adds 48 source scans relative to each dataset's
N24 fit, so any improvement would include that larger data budget.

## Numerical evidence

The [protocol](PROTOCOL.md) and [manifest](manifest.json) freeze source/target
membership, initializations and input/code hashes. All source IDs are unique
and disjoint from targets. Both source starts have 180-second worker caps;
target workers have 120-second caps. Qualification retains the earlier
optimizer, boundary, gradient and derivative gates. Target integration reuses
the audited scalar and 16/32-node checks, with predeclared 64/128 refinement
only for failed integrals. Original integration values are preserved.

The first batch launch occurred before preparation had written the manifest;
it failed at the missing-manifest read before starting a numerical worker.
After the original preparation process exited successfully, the batch was
launched. No duplicate fit or data-dependent restart occurred.

Per-start and per-target results and subprocess receipts accompany the
[summary](summary.json) and [table](TABLE.md). Source selection uses qualified
training likelihood only; numerical failures remain visible.

## Limits and reproduction

Both source starts passed all gates in 120.0 and 130.9 seconds. Their positions
agree within about 2 mm; that checks these starts, not global optimality.
Maximum source gradient was 0.00591 and maximum derivative replay discrepancy
was 3.91e−5. All 30 target integrals passed without refinement; maximum timing
quadrature difference was 0.005091 and scalar replay error 1.46e−11. Target
workers took at most 16.8 seconds each, 190.4 seconds summed. Input/code hashes
and fit-selection bindings verified, and Ruff passed. The existing audited
likelihood, optimizer and target integrator were reused without model changes.

The geographic reference is inherited, exposed and unsurveyed. The configured
center is already about 809 m from it. Candidate banks are site-conditioned,
timing/orbit truth is not independently established, and the fifteen targets
have been examined previously. The joint position is one estimate, not three
independent geographic successes. The combined pool spans more time than the
individual N24 pools. A better point estimate alone does not prove general
sub-km accuracy or calibrated predictive uncertainty.

No RF, production component, QNAP path or golden fixture is changed. Artifacts
are local research. Outputs use exclusive creation; reproduce in a fresh
archived-run context rather than overwriting completed evidence.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_joint72/study.py prepare
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_joint72/study.py batch fit
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_joint72/study.py select
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_joint72/study.py batch target
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_joint72/summarize.py
```
