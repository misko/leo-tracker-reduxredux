# Scan budget over a fixed temporal pool

Tests accuracy versus scan count while retaining the same baseline model and
the same 24-scan temporal pool in each dataset. Membership is frozen from
chronological ranks before geographic outcomes; no known error selects a set.

**Positive local geographic result: the full 24-scan fits reach 388m, 390m and
107m on DS7, DS8 and DS9 respectively.** All27 selected results qualify,
including nine reused eight-scan controls. This is not yet a validated default:
the same experiment's normalized interleaved held scores worsen with pooling,
and the reference site and prior are already exposed.

## Accuracy versus scan count

Cells are median errors over the declared sets; N24 is one estimate per dataset.

| Dataset | 8 scans, 3 sets | 12 scans, 2 sets | 16 scans, 3 sets | 24 scans, 1 set |
|---|---:|---:|---:|---:|
| DS7 | 1,416.56m | 880.99m | 707.65m | 387.52m |
| DS8 | 1,422.84m | 456.68m | 592.24m | 389.83m |
| DS9 | 1,042.82m | 987.05m | 307.13m | 107.23m |
| Sub-km sets across datasets | 3/9 | 5/6 | 8/9 | 3/3 |

The sixteen-scan exception is DS7 n16_0 at1,089.82m. DS8's median increases
between12 and16 scans, so improvement is not monotonic and a universal scan
threshold is not established. Full-pool start spans are10.25h,8.01h and12.61h
for DS7/8/9. These are not sixteen or twenty-four consecutive scans in a short
window. More active scan coverage within a long time span is the tested change.

![Geographic error and held-score behavior](budget.png)

The configured center-only prediction has809.03m error against the same
reference. All three N24 results improve upon it; crossing1km alone would not
establish a useful radio-derived estimate here. The inherited configuration
labels this center `inherited_ds6_development_donor; prior exposure unaudited`
and warns that candidate/track review products may be observer-site-conditioned.
This experiment does not resolve that conditioning or demonstrate blind location
recovery at a new site.

## Predictive evidence moves in the opposite direction

Coverage-normalized held log-score change relative to the N8 sets:

| Dataset | N12 | N16 | N24 |
|---|---:|---:|---:|
| DS7 | -170.764 | -145.874 | -187.985 |
| DS8 | -114.917 | -152.519 | -156.477 |
| DS9 | -156.036 | -157.511 | -183.944 |

Pooling forces one location to explain more tracks, while the smaller sets can
use different locations. Their interleaved held scores favor that flexibility,
even though their geographic estimates are worse. This is consistent with
systematic model errors that smaller groups can absorb; it does not identify
their physical cause. Do not suppress the negative predictive result or treat
the improved geographic errors as proof of calibrated uncertainty.

The next gate is prediction of scans outside these24-scan pools, selected
without consulting error or score, comparing N24 against both the center-only
control and a fixed N8 alternative. A shorter-latency consecutive-scan budget
study is also needed before giving an operational collection recommendation.

## Completion and checks

All18 new fits return zero after the preserved serialization correction and
have a qualified selected endpoint. Of108 new starts,107 meet the optimizer
gate; lower-scoring starts need not pass the final selection audit. Maximum
selected finite-difference discrepancy is1.34e-5; maximum timing-grid scalar
replay discrepancy is3.64e-12. Input/source bindings, exact session coverage,
and observation multiplicities verify at every budget. Manifest tests and Ruff
checks pass. Successful new jobs total1,423.88 process-wall seconds, maximum
129.08seconds, excluding the initial failed serialization attempt.

## Sets and model

| Scans per estimate | Sets per dataset | Membership | Per-scan evaluation multiplicity |
|---|---:|---|---:|
| 8 | 3 | Rank modulo3 | 1 |
| 12 | 2 | Rank modulo2 | 1 |
| 16 | 3 | Complement of each eight-scan group | 2 |
| 24 | 1 | Full pool | 1 |

Every set spans early/middle/late windows. The underlying pool is unchanged
from time_balanced_scans: 24 distinct recordings per dataset. Actual first-to-last
start spans are reported because endpoints differ slightly between subsets.
This spends more scans within roughly the same long elapsed window, rather
than claiming a lower-latency localization result.

The N8 points reuse the verified supplementary six-start fits. New N12/N16/N24
fits use the same q020 mixture, measurements, candidate banks and interleaved
training/held masks. Each fit has three zero-time starts and three training-only
timing-grid starts at the same fixed E/N coordinates. Starts qualify by optimizer
status, boundaries and gradient; candidates are then audited by descending
training score. Only a finite-difference-audited endpoint can be selected.
Reference location and held score do not select starts.

## Scores and limitations

For N16, every original scan appears twice. Half of the summed held log score
therefore gives each observation the same total weight as the other budgets.
This is an average of predictive scores over overlapping fits, not a single
joint predictive density, independent trial count, or calibrated uncertainty.
It is also still interleaved held-sample prediction, not unseen-scan validation.

N24 has only one estimate per dataset. Its table cell is a single result, not
robust repeated-set validation. The site and reference are inherited, exposed
and unsurveyed. Candidate identities remain conditional hypotheses. More data
can average errors without resolving incorrect associations or shared bias.

[Protocol](PROTOCOL.md) and `manifest.json` bind the frozen construction.
[Full table](TABLE.md) and `summary.json` retain every result and incomplete
budget. Per-set files record all six starts, selection audits, timing-grid replay,
coordinates, source/input hashes and process duration. The batch uses two
workers while a separately run DS7 N24 pilot can occupy a third slot. Every new
job has a180-second cap. No new RF, production edits or remote publication.

The first pilot encountered a final JSON serialization error for a NumPy boolean.
`pilot_failure.json` preserves the failure and correction. The unchanged fit was
rerun after converting audit metadata to ordinary Python scalar types.

```bash
python3 -m unittest discover -s reports/2026_09_29_scan_budget -p 'test_*.py'
python3 reports/2026_09_29_scan_budget/manifest.py
OPENBLAS_NUM_THREADS=1 timeout 180s uv run --no-project --with numpy --with scipy python reports/2026_09_29_scan_budget/run.py DS7_n24_0
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_scan_budget/batch.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_scan_budget/summarize.py
```
