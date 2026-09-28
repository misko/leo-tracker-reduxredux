# DS7 GLRT runtime and evidence recovery: bounded development protocol

This experiment reuses minted DS7 membership
`47007b1c18e8182f6a005dfd05c237cb3edb9bf85ae6376c99ccf29d54434109`.
It creates a derived benchmark view, not a new dataset or changed truth labels.
DS7 has prior research exposure. This is development evidence, not an untouched
holdout, independent-site result, or measured field false-alarm probability.

## Frozen initial selection

`plan.json` chooses the first chronological recording at each of 2.5, 5,
7.5 and 10 MS/s, then consecutive visits starting at the recording midpoint.
There are 16 visits at 2.5 MS/s and four at each other rate. Selection uses
metadata only and is frozen before reference GLRT outputs are generated.
Both receivers, all samples in each dwell, target order and actual source
counter gaps are retained. All selected dwells are 120 ms. The extracted
payload totals 124,800,000 bytes, below the frozen 512 MiB limit.

The public `AdaptiveHopIqStore(read_only=True)` verifies original manifests
and reads selected visits through its public reader. Local NPY files are
hash-bound in `inputs.json`; algorithms never construct backing-store paths.
No source payload, published contract, QNAP path, radio configuration or
production service is changed. The extraction is not a new full-corpus IQ
hash verification. The DS7 metadata verifier checks pose bindings but no pose
coordinate is supplied to any GLRT method.

## Baseline and methods

The baseline uses the original server acquisition and pilot modules preserved
before the portable optimizations, with SHA256s checked by `methods.py`.
The common scanner orchestrator retains its existing public decision rule:
eleven overlapping 20-ms probes, both receivers, eight acquisition candidates,
margin >=0.025 and a same-receiver non-overlapping pair within 8 kHz.

- `original`: full frozen original search and scoring.
- `optimized`: identical full workload with heap-based peak selection and
  immutable pilot-geometry caching.
- `candidates2`: retain and score two rather than eight acquisition candidates;
  every scheduled probe remains. This deliberately reduces evidence coverage.
- `local_fallback`: retain a previous freshly confirmed CFO per session,
  target, rate and receiver. For at most three seconds of source-counter age,
  search +/-20 kHz around it, bounded by the original +/-400 kHz domain,
  while still searching full timing and retaining eight candidates. Require
  fresh confirmation for each seeded receiver; otherwise rerun full blind
  analysis and include both attempts in timing. This is frequency-local,
  not a timing-prediction kernel. A success does not prove every other signal
  in the channel was found. An old failed track can remain dormant until its
  age limit; its previous decision is never reused as current evidence.

Each method receives only current IQ/context and its own earlier state.
Reference outputs are generated and sealed by the runner for later scoring,
never supplied to candidate code. Methods reset on independent repeats and
session changes. Shared-process interface separation is not a security sandbox.

## Execution and accounting

The serial experiment is pinned to CPU0, with numerical library threads=1,
nice=19, two complete chronological repeats and cyclic method-order rotation
within each visit. All methods start cold logically. Immutable library caches
may warm; no oracle-derived track initialization is permitted. Each method
object's construction cost is reported separately. The per-call CPU and wall
timer includes CI16 conversion, all search attempts and GLRT. Dataset loading,
hash checking and JSON serialization are outside that timer. Complete-run wall
time is also reported. Initial execution has a 1,800-second alarm; an incomplete
receipt is not a completed method comparison.

The benchmark is the complete detector, not full Standard waterfall/Doppler
analysis, PNG rendering, storage publication or a live scanner. High-rate
support is native; no resampling or relabeling between rates occurs.

A separate four-worker execution arm may process the same complete probe
inventory concurrently. It must return exactly the original chronological
result and report parent plus worker CPU, wall latency, initialization and
four-core resource use. It is a latency comparison, not a one-core CPU saving.
It runs after the serial matrix, avoiding benchmark-on-benchmark contention.

## Scoring and admission

`SCORING.md` defines matching before numerical outcomes are inspected.
Use exact full-output equality for invariant-workload methods. For approximate
searches, report confirmed receiver-visit recovery, positive hypothesis
recovery with one-to-one timing/CFO matching, and added positive hypotheses.
Matched-hypothesis confirmation is separate from merely remaining active on
the same channel. Missed, failed and unprocessed units stay in denominators;
zero positive denominators are N/A. Extra candidates are not labelled physical
false alarms. Receiver/probe/mode scores are reference-relative, not truth.

Main scientific counts use one chronological repeat; the second verifies
repeatability rather than doubling independent sample size. Runtime uses both
repeats. Publish every method/rate and all failures, including regressions.
Report the weighted cohort timing and rate-stratified timing; do not imply that
this cohort's rate mix represents all 88 recordings.

No approximate method is promoted as equivalent based only on activity recall.
Scientific shortfalls are experimental findings, not grounds to tune a gate on
these cases. Broader chronological groups and independent constructed controls
are required before integrating a reduced-search policy into production.
