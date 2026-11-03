# Capture-bracket timing constraints worsen the full nine-panel comparison

**Do not promote this timing model.** All nine selected fits pass the numerical
audit, but held prediction worsens on every panel and geographic error improves
on only two. Every dataset's eight-scan median error increases. The fresh q020
free-timing baseline remains the comparison model.

| Dataset | Panels audited | Free-timing median error | Shared bias + brackets median error |
|---|---:|---:|---:|
| DS7 | 3 / 3 | 2,023.56 m | 2,170.80 m |
| DS8 | 3 / 3 | 1,721.07 m | 1,756.63 m |
| DS9 | 3 / 3 | 876.13 m | 2,613.24 m |

Each median includes the complete early/middle/late eight-scan set. These are
joint scan-set estimates, not single-scan errors. Nominal sub-km panels decline
from two to one. DS8 early improves to 421.30 m, but that isolated exposed-reference
result is not used to select a model. Late DS9 worsens to 5,494.07 m and remains
in every planned denominator.

![Complete geographic and held-score comparison](comparison.png)

## All planned outcomes

| Panel | Baseline error m | Bracket model error m | Held score change nats | Active capture bounds | Audit |
|---|---:|---:|---:|---:|---|
| DS7 early 8 | 2,286.00 | 2,368.82 | −271.67 | 5 / 8 | Pass |
| DS7 middle 8 | 1,603.57 | 2,170.80 | −217.17 | 6 / 8 | Pass |
| DS7 late 8 | 2,023.56 | 1,931.09 | −52.47 | 8 / 8 | Pass |
| DS8 early 8 | 1,435.66 | 421.30 | −264.20 | 6 / 8 | Pass |
| DS8 middle 8 | 2,130.85 | 2,438.34 | −643.23 | 5 / 8 | Pass |
| DS8 late 8 | 1,721.07 | 1,756.63 | −494.69 | 6 / 8 | Pass |
| DS9 early 8 | 639.50 | 1,073.16 | −447.06 | 7 / 8 | Pass |
| DS9 middle 8 | 876.13 | 2,613.24 | −323.81 | 6 / 8 | Pass |
| DS9 late 8 | 3,680.86 | 5,494.07 | −678.59 | 7 / 8 | Pass |

Positive held change would mean improvement. Training score also declines on
all nine panels, by 173.66–1,006.19 nats, consistent with the model restriction.
Capture deviations contact their allowed bounds in 56/72 recordings. This
substantial pressure against the constraints reinforces that the current
likelihood needs more than physical capture-time uncertainty alone.

## The assumption tested

The independent [timing audit](../2026_09_29_timing_authority/README.md) verified
roughly 364-ms-wide first-sample host brackets. Here recording time is
`tau_i = shared_host_bias + capture_deviation_i`, with each deviation confined
to its measured bracket relative to the midpoint. One common host bias is fitted
per eight-scan panel. Host UTC stability across a panel is an explicit assumption;
the metadata does not provide historical absolute UTC discipline evidence.

Keep shared position, unchanged q020 background probability, Student-t4/100-Hz
signal contrast likelihood, candidate banks, noise model, observation masks and
all 4,328 eligible tracks from 72 scans. No candidate is relabeled or removed.
This changes only timing parameter constraints. Position bounds stay at ±12 km;
bias bounds ensure every permitted recording time remains inside the original
±5-second orbital-state bank. Neither selected position nor bias hits its outer
bound. Fitted bias ranges from −1.343 to +0.066 s across panels, but those values
are model parameters, not independently measured clock errors. Bias/deviation
decomposition may be nonunique when constraints permit a common shift.

The reference is the same previously exposed, operator-entered, unsurveyed
37.849056280893684, −122.48575489722863 used in earlier reports. This is a
development sensitivity test at one site, not independent accuracy validation.
No start, bound or model is selected using that reference or held observations.

## Numerical qualification and execution

The [protocol](PROTOCOL.md) preceded fitting. Three starts per panel project the
free-timing solution into measured brackets with bias shifts −0.25, 0 and +0.25 s.
All **27/27 starts qualify** under the declared success, projected-gradient and
outer-bound requirements. Highest training score selects the reported fit.
Maximum selected projected gradient is 0.000554, below the 0.01 gate. A separate
feasible finite-difference audit of the transformed gradient passes all nine;
maximum discrepancy is 0.002303, below 0.02. Nearby starts and local gradient
audits do not establish global optimality.

Three synthetic tests pass: chain-rule gradient, feasible timing-bank bounds
and common-shift invariance, and correct projected-gradient signs at boundaries.
Every baseline training score and held row is replayed within 1e-7, all declared
observation/manifest/bank digests are verified, and matched held track identities
and observation counts are checked. Baseline geographic errors reproduce the
prior q020 summary within 1e-4 m. Ruff lint/format pass.

The initial DS7 early run completed numerical work but failed serializing a
NumPy scalar, producing no result JSON. The explicit [execution note](EXECUTION-NOTE.md)
records the writer repair and administrative rerun exception. The corrected
batch has nine successful process receipts and no retries, timeouts or numerical
qualification failures. Total corrected child time is 130.85 seconds; the longest
child is 17.83 seconds, within its 120-second cap. Children ran sequentially with
one numerical thread. No RF collection or production edit occurred.

Per-panel JSON retains every start, selected parameters, gradients, audit,
complete held rows, baseline rows and source/input hashes. `summary.json` retains
every panel and all dataset medians; [TABLE.md](TABLE.md) is generated from those
same results. Logs and receipts preserve process outcomes.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_host_bracket_position -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_host_bracket_position/launch.py
.venv/bin/python reports/2026_09_29_host_bracket_position/summarize.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_host_bracket_position/plot.py
```

## Next decision

Do not interpret the free fitted recording times as capture latency, and do not
replace them with these host constraints in the present likelihood. The measured
timing authority is useful evidence, but a physical timing constraint alone does
not repair the remaining orbit/association/signal-model mismatch. Further work
should investigate why candidate frequency shapes require those time shifts,
using independent signal or identity evidence rather than choosing a timing
strength from the geographic table. Reliable short-window sub-km accuracy remains
unresolved.
