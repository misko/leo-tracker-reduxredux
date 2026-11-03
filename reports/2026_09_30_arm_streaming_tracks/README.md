# Chronological GLRT tracking: SOL implementation comparison

Three SOL agents implemented independent research trackers. All were tested on
the same frozen 300-second DS9 scan, with both ARM and server GLRT detections,
and benchmarked on physical PLUTO+ at 192.168.1.15. The rolling linear method
is the fastest new implementation. The earlier coarse-seeded curvature method
still provides the best measured coverage/runtime combination on this scan.

## Approaches

1. **Rolling linear:** chronological source groups; weighted straight-line fit
   to the last 8 seconds, at most 32 observations; bounded competing hypotheses
   and recent births. The whole trajectory can curve as its local slope changes.
2. **Frequency/rate Kalman:** evolving frequency and slope, acceleration process
   noise, innovation gating, missed-detection branches, and rolling births.
   V2 clusters near-duplicate histories before capacity selection.
3. **Local tracklet linking:** short linear segments in overlapping 8-second
   windows stepped by 4 seconds; link using local endpoint frequency/slope.
   V2 allocates distinct fragment capacity per window to preserve late evidence.

These are batch research CLIs. The first two traverse observations in time, but
their public interfaces still accept a complete batch and retain output history.
They are not yet persistent online services with bounded end-to-end latency.
The third is a windowed construction/linking approach, not a strict single pass.
All outputs are overlapping hypothesis banks, not exclusive satellite identities.

## Main results

“Represented” means at least one output satisfies the frozen >=80% source
coverage and >=80% in-span source purity gates, comparing CFO modulo alias within
2500 Hz at identical canonical sources. Ref 10 is explicitly excluded at user
request, leaving 62 reviewed server segments. Ref 35 remains included despite
its known purity-metric limitation. These counts measure server agreement,
not independently verified physical identities or false-positive rates.

| Method | Represented using ARM detections /62 | Represented using server detections /62 | ARM output hypotheses | PLUTO+ tracking seconds, ARM input | Host tracking seconds, ARM input | Causal prediction p95, ARM input |
|---|---:|---:|---:|---:|---:|---:|
| Rolling linear, 8 s | 39 | 58 | 327 | 1.119 | 0.0272 | 486 Hz |
| Kalman v2 | 33 | 47 | 125 | 11.742 | 0.1767 | 426 Hz |
| Local tracklet linking v2 | 40 | 53 | 123 | 14.962 | 0.2491 | 706 Hz |
| Earlier coarse-seeded curvature | 49 | 62 | 62 | 3.543 | — | 462 Hz |
| Earlier pair-seeded curvature | 46 | 46 | 55 | 42.797* | — | 485 Hz |

Times are reconstruction only. New-method host and ARM-input device values
are medians of three repeats; *pair-seeded curvature is the earlier single
physical measurement. The hybrid 3.543 s includes coarse-seed reconstruction
plus curvature extension, not extension alone. Its intermediate TSV handling
and process startup appear in whole-process timing below.

The fresh standard-server control takes **8.321 s** median for lane tracklet
reconstruction, and **9.701 s** for full reconstruction including grouping and
graphs, on the server host. All three reruns serialize identically to the frozen
reference. This is different hardware/language/algorithm from the ARM methods;
ratios are not same-algorithm speedups. See `server-control-timing.json`.

The common fit diagnostic predicts each next CFO from an unweighted linear fit
to the preceding 8 s, requiring five prior points spanning 2 s and a next gap
at most 4 s. It uses circular residuals and no future observations. Server
reference p95 is 405 Hz. A low error does not establish correct identity:
duplicate or truncated tracks can have excellent residuals while missing many
segments. Prediction counts and detailed distributions are in each evaluation.

## Timing scope and reproducibility

| Method | PLUTO+ whole process, ARM input | Max RSS | PLUTO+ tracking, server input (one run) |
|---|---:|---:|---:|
| Rolling linear | 2.048 s | 9460 KiB | 1.212 s |
| Kalman v2 | 12.541 s | 8184 KiB | 10.361 s |
| Local tracklet linking v2 | 15.517 s | 7260 KiB | 17.021 s |
| Coarse-seeded curvature | 4.633 s | 7492 KiB | not newly measured |

Whole-process timing includes parsing, process setup and output serialization;
tracking-only values exclude them. Neither includes GLRT, IQ reading/transfer,
capture, satellite association, or positioning. Each hardware replay processes
already saved observations. No RF, firmware change or production activation
was performed. This does not qualify concurrent continuous adaptive scanning.

Every tested device output is byte-identical to its corresponding host output.
All three host repeats per input also agree byte-for-byte. Binary and input
hashes, per-run timings, stdout, stderr and device unit-test receipts are in
`qualification/<method>/`. Hybrid receipts also verify regenerated coarse
seed output against its frozen host result. `summary.json` is machine-readable.

## What the experiments established

- Rolling linear recovers refs 19/33/59, which the original globally ranked
  pair seeds missed. Its remaining adequate-input losses include truncated or
  fragmented associations, and it emits many near-duplicate alternatives.
  Differences from the earlier curvature implementation also include birth,
  branching and retention policy; this is not a controlled proof that explicit
  quadratic curvature is necessary.
- The first Kalman implementation represented only 14 segments on either input
  and took 14.651 s on ARM. One targeted history-deduplication revision raises
  agreement to 33 ARM /47 server, showing candidate management matters. It
  still underperforms the rolling and hybrid implementations here.
- The first linking implementation represented 9 ARM /13 server segments and
  took 5.004 s. It filled its chronological global fragment cap early. Giving
  every window bounded distinct capacity raises agreement to 40/53, with higher
  runtime. This diagnoses an implementation issue, not failure of tracklet
  linking as an algorithm family.
- The prespecified rolling-window sensitivity gives ARM counts 38/39/40 for
  4/8/12 s and server counts 56/58/58. The 12 s case emits 347 ARM hypotheses.
  Sensitivities are host-only and are not substituted for the primary 8 s result.
- Eleven reviewed server segments have less than 80% matching ARM input
  evidence under this comparator. No association method can meet that exact
  source-coverage criterion without additional detections; physical recognition
  from fewer points is a separate question.

The two-curve synthetic fixture has known memberships, curvature, aliases,
gaps and clutter. Rolling and Kalman v2 each recover both curves under the
80% coverage/purity criterion; linking v2 recovers one. Passing this fixture
does not imply parity on the recorded scan.

Keep the coarse-seeded curvature method as the current quality baseline.
The rolling method is a promising starting point for a streaming component,
but needs distinct-track retention, controlled ambiguity handling, and recovery
validation before replacing that baseline. The current evidence does not
justify switching production to any of these first implementations.

## Validation and evidence

All five implemented versions passed their component tests on optimized host,
ASan/UBSan, and physical ARM. Tests cover relevant curved paths, crossings,
aliases, gaps, clutter and timestamp handling; the revisions add late-window
coverage or duplicate-history regression cases. Three independent evaluator
tests check causal fitting, alias invariance and gap exclusions. The strict
parser validates source authority, normalized CFO, alias sign and support bounds.
Rejected normalization/timing/serialization attempts are preserved separately
and never included in the tables.

The original protocol and hashes precede shared scoring. V2 revisions are
explicitly post-result, targeted implementation corrections, not independent
untuned confirmations. No scientific golden fixture or threshold was changed.
The archived hybrid README/receipt mistakenly said 62 server-input hypotheses;
the hash-bound TSV actually has 71. A fresh rerun reproduces those exact bytes;
`hybrid-server-count-audit.json` records the reporting correction. ARM hybrid
output remains 62 hypotheses. All coverage measurements use actual TSV contents.

Plots show measured assigned CFO points, not global compatibility fit lines:

- [Rolling overlay](qualification/rolling/comparison.png)
- [Kalman v2 overlay](qualification/kalman-v2/comparison.png)
- [Tracklet linking v2 overlay](qualification/linking-v2/comparison.png)

Component descriptions and receipts: [rolling](rolling/README.md),
[Kalman v2](kalman-v2/README.md), [linking v2](linking-v2/README.md).
`run_host.py`, `run_device.py`, `benchmark_hybrid.py`, `evaluate.py` and
`summarize.py` reproduce the qualification workflow with new output directories.
