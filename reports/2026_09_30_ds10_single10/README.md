# Ten localization methods on eight individual DS10 scans

All ten methods have eight qualified single-scan results. The correlation variants lead this pilot: q020 with correlation has median reference distance **1363 m**, and shared-scale correlation **1423 m**, versus **2009 m** for the original independent Student-t baseline. Both improve distance on seven of eight scans. Neither establishes a sub-kilometre single-scan method.

This is a matched pilot on eight deterministically time-spread scans from the existing DS10 N24 panel, spanning 23.83 hours. Each scan independently estimates one location and one timing offset. It is not an eight-scan joint fit or an evaluation of all 187 DS10 recordings. The data and roof reference were previously exposed; this is development evidence, not blind validation.

All distances use the unsurveyed roof reference and mean Earth radius 6371008.8 m. The fixed configured center is already about 809 m away. DS10 installation/reference continuity remains unconfirmed. Qualified optimization does not establish absolute accuracy.

## Results

| Method | Median m | P90 m | Maximum m | Below 1 km | Qualified | Median runtime s |
|---|---:|---:|---:|---:|---:|---:|
| q020 plus 10 s correlation | 1363 | 4407 | 8289 | 1/8 | 8/8 | 2.36 |
| Shared scale plus 10 s correlation | 1423 | 4318 | 8243 | 1/8 | 8/8 | 2.16 |
| Shared scale, no correlation | 1938 | 5213 | 10057 | 0/8 | 8/8 | 2.31 |
| Shared scale plus 40-degree cones | 1943 | 5189 | 9974 | 0/8 | 8/8 | 3.71 |
| Frequency contrasts | 1953 | 5213 | 10074 | 0/8 | 8/8 | 2.21 |
| Original independent Student-t | 2009 | 5128 | 8461 | 1/8 | 8/8 | 20.73 |
| q020 plus shared curvature | 2100 | 5499 | 10229 | 1/8 | 8/8 | 5.11 |
| q020 | 2347 | 5212 | 10224 | 0/8 | 8/8 | 2.16 |
| q020 plus 40-degree cones | 2359 | 5170 | 10104 | 0/8 | 8/8 | 4.36 |
| q020 plus shared candidate slope | 2449 | 5277 | 10365 | 0/8 | 8/8 | 5.41 |

P90 uses linear empirical interpolation over eight values and is imprecise with this small sample. All methods qualify on the same eight scans, so no changing-denominator advantage affects medians. Runtime includes process startup, input loading, three starts and numerical audits; slope and curvature also include their required single-scan q020 prerequisite. Runs used at most two concurrent processes, one BLAS thread each. Engineering retry overhead is preserved separately rather than included in successful-model runtime.

The ten methods are existing serious contenders and scientific controls, not ten methods previously proven to outperform the baseline. Cone angles are half-angles. The shared-scale cone arm uses soft candidate compatibility; the q020 cone arm routes rejected satellite mass to background. These are distinct implemented formulations.

[TABLE.md](TABLE.md) contains full min/max metrics and all 80 per-scan distances. [metrics.csv](metrics.csv) and [summary.json](summary.json) provide machine-readable aggregates and cells. [plan.json](plan.json) binds full session IDs and artifact digests. S1–S8 correspond to indices 0, 3, 6, 9, 13, 16, 19 and 23 of the frozen chronological N24 panel.

## What changes our assessment

Correlation deserves renewed testing specifically for single-scan localization. Relative to the original baseline median, shared-scale correlation improves by **29.2%**, and q020 correlation by **32.2%**. Both improve seven of eight paired scans; their maximum errors still exceed 8 km. Previous adverse pooled/other-dataset evidence remains relevant, so this pilot does not justify universal promotion.

The two correlation methods differ by only about 61 m in median reference distance. That is not sufficient to establish that the extra background component is warranted. The simpler shared-scale correlation arm has slightly better P90 and maximum distance here. q020 without correlation is **16.8% worse** in median than the original baseline, confirming that better predictive modeling does not automatically improve location.

Nominal cones add no material median benefit. Shared slope and curvature do not earn their extra complexity on this population. The independent model remains much slower in the current implementation. The next matched test should carry both correlation leaders and the simpler shared-scale/no-correlation baseline onto larger fixed single-scan samples and identical N8/N24 populations, without changing parameters based on these reference distances.

## Common predictive diagnostic

Each qualified point is also evaluated with the same q020 held-observation model. Summed held-score changes relative to q020's own fitted point are: original −63.949; shared scale +12.191; shared correlation +1.436; contrasts +10.752; q020 0; correlated q020 −6.305; shared-scale cones +12.399; q020 cones −0.986; shared slope +6.730; shared curvature −43.821.

This is a common-model diagnostic of the fitted points, not each method's native predictive likelihood. It uses the existing within-track held masks and reused candidate banks, not independent future scans. The location winner is not the predictive winner. Do not rank incompatible native likelihood definitions as if they shared a single score scale.

## Qualification and preserved failures

The [protocol](PROTOCOL.md) predates fitting. Each method uses three fixed location starts with zero timing, selecting only by qualified training likelihood; no pooled estimate or reference distance seeds/selects a fit. Of 240 optimizer starts, **237 qualify**, and every one of the 80 scan/method combinations has a qualified selected result. Slope/curvature numerical integration also passes the 128-versus-256-node audit on selected results. All attempted scans are retained.

The first six slope/curvature adapter attempts failed before fitting because list-valued timestamps needed NumPy conversion for boolean indexing. The [amendment](AMENDMENT.md), original source, logs and receipts preserve these engineering failures. The corrected six retries all complete successfully under the unchanged budget; no scientific failed fit is retried or hidden. No process reaches its 90-second timeout.

Two metric tests pass. Every selected fit passes optimizer success, interior-bound, gradient and finite-difference audit gates. The manifest hashes are checked on loading. Source and result hashes are sealed. The code reuses existing model implementations and their previously tested likelihoods; no production component or golden fixture changed.

No new RF, raw-IQ processing, production change or remote publication occurred.
