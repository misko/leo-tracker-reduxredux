# Catalogue reuse and predictive precision on the current dense saved solver

DS30-0173 and DS30-0359 share **zero verified catalogue body digests**. The
current DS30-0359 process already reduced its 134 authenticated reads to 41
strict body parses. A distinct predictive-grid prototype cut **43.214 ms**
from **100.980 ms** on 32 paired calls. The **0.481 CPU s** full-grid scale
estimate missed the frozen **0.5 s** gate. The original solver, grid and
publisher remain unchanged.
[Protocol](ds30-0359-precision-slice-protocol.md) ·
[Machine receipt](measurements/ds30-0359-preparation-and-precision.json.gz)

## Chronological catalogue reuse

| Original saved request | Snapshot references | Distinct content digests | Bytes across references | Bytes counted once per digest |
| --- | ---: | ---: | ---: | ---: |
| DS30-0173 | 51 | 35 | 91,144,362 | 62,549,089 |
| DS30-0359 | 47 | 41 | 83,998,561 | 73,272,684 |
| Common exact body digests between requests | | **0** | | **0** |

The signed original cutoffs differ by 73.190 hours. The intersection uses
content digests, independently of snapshot timestamps. The read-only roster
check opened the staged admission receipts and DS30-0359's as-run ports
receipt. The DS30-0173 admission had previously verified its catalogue
against the local NVMe collector. The DS30-0359 admission used existing
tmpfs hard links. This experiment used their already resident copies and
made no new archive copies. SHA-256 of the receipt inputs and their exact
filename-roster digests are recorded.

Through normal cold guarded preparation, DS30-0359 took **2.472 elapsed /
2.470 CPU s**, including **134 reads of 239,498,102 bytes** across 45
snapshot names. Each read retained the ordinary confined path, original SHA
and ASCII validation. The live source index deduplicated body parsing by
digest and first materialization by exact two-line text, producing 104,797
distinct source pairs. At different collection stamps the original election
and regional work still apply. Neither a matching NORAD nor a prior
successful digest check supplies a later cutoff or proves the current
readable bytes. Forty-five first reads by filename account for 80,425,565
bytes. The difference is repeated authenticated traffic, with no new
measured saving assigned to it. The earlier DS30-0173 worker similarly
verified 128 reads and 228,741,991 bytes with 35 body parses and
98,196 distinct source line pairs in 2.270 CPU s.
[Active reader and index](historical_orbit_index.py) ·
[Clean saved worker](ds30-0359-composed-saved.md)

| Earlier experiment | Attributable result and cost |
| --- | --- |
| Catalogue prime, DS30-0008 | Parser CPU fell 0.508 → 0.008 s, with 0.657 s primer CPU. Paid elapsed rose 3.227 → 3.311 s. [Measurement](catalogue-prime.md) |
| Persistent strict records, DS30-0016 and DS30-0057 | Even granting free reuse for 19 and 17 known bodies saved an ideal 0.077 and 0.070 CPU s. Original SGP4 construction still took 0.198 and 0.233 s. [Measured ceiling](tle-source-cache-ceiling.md) |
| Persistent orbit transitions, DS30-0016 → DS30-0057 | 82 of 9,040 later transitions matched. Forecast CPU rose 40.53 ms across both requests, including first use, and second-request peak RSS grew by 9.74 MiB. [Measurement](persistent-orbit-updates.md) |
| Prepared portable catalogue, DS30-0306 → DS30-0316 | 37 of 40 bodies were already available. Preparation CPU fell 2.283 → 1.902 s. The earlier producer took 1.231 s elapsed, and charged first use took 12.314 s compared with 11.695 s ordinary saved publication. [Measurement](portable-orbit-0316.md) |
| Causal live election, DS30-0289 | All 126 reads and both published arms remained identical. Preparation CPU rose 9 ms, or about 14 ms with the binding. [Measurement](causal-live-election.md) |

The zero digest intersection rules out carrying immutable parsed bodies
across this specific chronological pair. Repeated parsing within either
request was already eliminated. Earlier donors with larger intersections
establish smaller savings under the original authentication and first-use
boundaries. This evidence gives no basis for a new persistent catalogue
cache or for dropping validation calls.

## Predictive computation with a smaller linear system

The actual clean DS30-0359 worker spent **3.410 CPU s** on the complete
179-position grid, including **1.898 s** of curved calculations and
**1.212 s** in the predictive-kernel clock. A prior same-input paired
diagnostic directly attributed the current reduced predictor's CPU to
**0.536 s** posterior whitening, **0.299 s** bias marginalization, and
**0.367 s** remaining factor and readout. No zero-column prefix occurred
in its 356 fresh calls. The curved posterior already has a measured
cross-arm reuse study, and separate fixed-Gram and four-location tests
priced the adjacent arithmetic.
[Predictive clocks](ds30-0359-predictive-grid.md) ·
[Curved posterior audit](grid-cross-arm-posterior.md) ·
[Four-location comparison](location-batched.md)

The prototype forms the predictive normal equations in the exported
posterior-coefficient order. It adds the original posterior precision to
the weighted design Gram, then deducts a rank-one correction per
independent predictive curve bias. It solves the resulting system once
and rotates back to the original residual representation. Posterior
whitening of all 1,133 observation rows is no longer required. Both
kernels charge array construction, factorization, normalization and
residual readout for every call. No result transfers across arms or
locations.

| Paired actual operands | Incumbent CPU ms | Prototype CPU ms | Maximum objective difference | Maximum residual component difference |
| --- | ---: | ---: | ---: | ---: |
| 16 fixed-zero calls | 49.916 | 28.418 | 5.457e−12 | 7.857e−13 |
| 16 fitted-`c` calls | 51.064 | 29.348 | 7.276e−12 | 7.940e−13 |
| **32 calls** | **100.980** | **57.765** | **7.276e−12** | **7.940e−13** |

The tested rows had 63 bias groups, 188 or 189 parameters, and exact
normalization on every call. The paired elapsed clocks were **100.974 →
57.744 ms**. Complete authenticated grid input was retained and the worker
consumed the incumbent result throughout. The observation stopped at
fresh call 46 in both arms, after the prespecified 32 pairs. The diagnostic
emitted no position, grid or image publication. A different accumulation
order and the use of normal equations require full-grid and conditioning
qualification before any production use.

Scaling the **42.8%** paired kernel reduction to all 356 calls yields
**0.481 CPU s** under equal mean per-call cost, before any independent
qualification or deployment expense. This is below the frozen threshold
and below the **0.707 elapsed s** / **0.715 CPU s** gap from the clean
saved worker to half of the fresh installed clock. Extrapolation supplies
no full-process credit. Four preliminary invocations stopped before
scientific work because of isolated import, admission serialization,
tmpfs path and missing binding errors. They took 0.04, 0.05, 0.09 and
0.11 s elapsed respectively. The corrected invocation took **12.28 s
elapsed / 12.09 CPU s** through exit with 38 major faults and 83,880 input
blocks. Those are whole-process counters without file-level attribution.
The backing-open guard remained active. No survey or waveform was read.
[Fresh installed comparator](ds30-0359-installed-control.md)

## Reproduction

Use the released Python with `-IB` under the existing shared Gauss
lease. Pin CPU 2, nice 15, best-effort I/O priority 7, and each numerical
thread environment variable to 1. Point `MPLCONFIGDIR` at the existing
authorized font cache. Run `ds30_0359_precision_slice.py` with a fresh
private child of `/dev/shm`. The observer validates the original
admission, binding, paired grid receipt and signed job before initiating
the normal saved route. Two focused component tests cover the rotated
residual and objective after a nontrivial ordering, and unsorted group
rejection.
[Observer](ds30_0359_precision_slice.py) ·
[Prototype](grid_predictive_precision.py) ·
[Tests](../../../tests/pipeline_eval/test_grid_predictive_precision.py)
