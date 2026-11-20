# One anchor set for the complete capture GLRT

One 12-anchor pass saved **12.7% of complete detector CPU** and dropped **3 of 36 original winners** on 64 outcome-blind dual visits. One 22-anchor pass used **82.9% more CPU**, retained 35 of 36 original winners within the matching tolerance, and added gated output on three reference-negative receiver-probes. The original conditional detector recovered all 16 forensic targets. The one-pass alternatives recovered 7 with 12 anchors and 11 with 22. [CPU and signal stage figure](stage.pdf) · [Audited data](summary.json)

The capture producer starts both receivers on 12 anchors. A gate-passing primary can trigger one 22-anchor retry on its peer. That retry replaces the entire peer result, including rejected candidates. The two alternatives evaluate each receiver once with either the original 12-anchor set or the original 22-anchor set. All three use the same prepared grid, row-wise selector, eight-candidate budget, and CFO, integer GLRT, and fractional refiners. [Protocol](PROTOCOL.md) · [Bound inputs and producer sources](input-lock.json)

The earlier capture-starts work traced which branch supplied particular targets and tried the primary coarse stage as a timing hint. The earlier raw-boundary work disabled the retry on two selected DS26 visits. This study runs both one-pass alternatives through the full capture detector across an outcome-blind held sample and separately tests all 16 predeclared wide-detector misses. [Capture-starts trace](../../acquisition-frontier/capture-starts/README.md) · [Earlier raw-boundary controls](../../detector-origins/raw-boundary/README.md)

## Complete detector runtime and output

| Anchor policy | Mean / median / P95 CPU per dual visit (ms) | Mean coarse grid CPU (ms) | Field-equal complete visits | Original winner recovered | Exact original winner present | Additional admissions among 92 original negatives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Conditional 12 then 22 | 713 / 577 / 1,326 | 303 | 64/64 | 36/36 | 36/36 | 0 |
| One 12-anchor pass | 623 / 572 / 905 | 236 | 55/64 | 33/36 | 33/36 | 0 |
| One 22-anchor pass | 1,305 / 1,301 / 1,745 | 904 | 0/64 | 35/36 | 24/36 | 3 |

Five interleaved repeats per held visit produced 320 complete timings per arm. The measured path begins with resident dual CI16 and ends after projection. It includes the original refiners and their numerical fallbacks. On the nine retry visits, one 12-anchor pass saved a paired median **684 ms**. The paired median difference on the remaining 55 visits was **+0.7 ms**, with field-equal public results on all 55. The experiment ran on busy Intel Core Ultra 9 285K CPUs 12–15 with one thread per worker. Every measured dual visit exceeded 20 ms wall time. The physical timing and candidate counts apply to this held sample. [Per-repeat times](timing.csv) · [Per-visit parity](visits.csv) · [Per-lane decisions and inventories](lanes.csv)

Each arm emitted 1,024 public candidate records in the held panel. The conditional, 12-anchor and 22-anchor policies respectively projected 564, 560 and 606 complete fractional candidates, including 108, 104 and 140 gate-passing records. The 22-anchor arm still admitted the receiver whose original winner it missed, with a different gated timing or CFO. [Complete candidate payloads](qualification-lock.json)

| Held recording and edge | Conditional retries in 16 visits | RX0 / RX1 retries | Successful retries | Mean CPU change for one 12 / one 22 |
| --- | ---: | ---: | ---: | ---: |
| DS26-0162 upper | 4 | 3 / 1 | 1 | −20.1% / +55.1% |
| DS26-0237 lower | 3 | 1 / 2 | 2 | −17.6% / +92.4% |
| DS29-0082 upper | 0 | 0 / 0 | 0 | +0.4% / +105.2% |
| DS29-0519 lower | 2 | 0 / 2 | 0 | −12.1% / +84.2% |

The 16 DS29-0082 held visits happened to contain zero retries. Its recording-wide archive establishes at least 782 among 4,868 valid visits. [Recording-wide bounds](summary.json)

The 22-anchor pass recovered all nine forensic winners originally supplied by the retry, and only two of seven originally supplied by the primary. The 12-anchor pass recovered all seven primary-origin targets with exact values. This accounts for both failure modes of making the anchor set unconditional. [Forensic rows](forensic.csv)

## Complete archived retry evidence

The full DS26-0237 archive identifies **1,592 of 6,766 valid visits (23.53%)** with a 22-anchor retry. The retry reached the gate on **448** of those visits. A 12-anchor-only schedule removes exactly those **448 of 3,740 gated receiver-probes (12.0%)** and admits no new receiver-probes. The ledger identifies the occurrence of a retry regardless of its outcome. Failed retries are assigned to the final negative lane. Successful retries have two final positives and their receiver is ambiguous in the ledger. [Complete selector ledger](../../receiver-deadline/selector-waveform/cache.csv) · [Archive census and source hashes](summary.json)

| Recording and edge | Valid archived visits | Visits with retry | RX0 retries | RX1 retries |
| --- | ---: | ---: | ---: | ---: |
| DS26-0162 upper | 6,713 | 789–3,153 | 331–2,695 | 458–2,822 |
| DS26-0237 lower | 6,766 | 1,592 | 279–727 | 865–1,313 |
| DS29-0082 upper | 4,868 | 782–1,325 | 178–721 | 604–1,147 |
| DS29-0519 lower | 6,727 | 1,047–2,842 | 156–1,951 | 891–2,686 |

DS26-0237's ledger records 104,286 inverse FFTs per full 12-anchor grid and 191,037 per full 22-anchor grid on the same 21 × 13,333 lattice. The measured visit totals uniquely resolve the mix. A conditioned-CFO tie can repeat the acquisition with direct scoring. These internal repeats account for some three-grid visits without a peer retry and some four-grid visits with a retry. The fresh assay cross-checks the inferred branch against the actual instrumented call on every DS26-0237 held and forensic visit. For the other archives the final gates give exact counts for lone positives and bounds for dual positives. The per-receiver maxima are individual bounds. [Prepared grid evidence](../../original-support/original-kernel/README.md) · [Verification and full visit payloads](qualification-lock.json)

## Reproduce the held assay

Use a new scratch directory on the local corpus host. Run the frozen sample on assigned host cores and publish into an evidence directory. The installed producer roots and libraries are hashed by the lock. [Assay source](../../../../tools/pipeline_eval/qualification/single_pass_trial.py) · [Report generator](../../../../tools/pipeline_eval/qualification/single_pass_results.py) · [Component tests](../../../../tests/pipeline_eval/test_single_pass.py)

```bash
work=/srv/bulk/leo-dev/single-pass-reproduction
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_trial freeze "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_trial run "$work" DS26-0162 12
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_trial run "$work" DS26-0237 13
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_trial run "$work" DS29-0082 14
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_trial run "$work" DS29-0519 15
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_results "$work" --out "$work/report"
.venv/bin/pytest -q tests/pipeline_eval/test_single_pass.py
```
