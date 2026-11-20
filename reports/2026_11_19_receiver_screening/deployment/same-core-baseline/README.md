# Same-core production v5 and compact secant

Across four complete same-core pairs, five-refresh compact secant was **3.65× faster** at the median from launcher entry to usable output. The median ratio was **3.42×** for logged numerical work through each method’s own published boundary and **2.34×** for the common named stages through cavity. Median child CPU fell by a factor of **3.69**. All four original jobs produced and revalidated their scientific archive and eight PNGs. All eight positions and their conditional RMS values reproduced the corresponding originals exactly. The eight compact arms independently reproduced their canonical compact archive exactly. [Two-arm position chart](charts/index.html) · [Timing scopes](timings.csv) · [Sealed inputs and schedule](source-lock.json)

The four cases were hash-selected across the upper and lower archived runtime halves for each dataset. Each fresh pair used the same stored GLRT, causal catalogue, tile, scientific request, one pinned CPU and one BLAS thread. Method order alternated. The host was an Intel Core Ultra 9 285K running Linux. The full set of receipts landed 547.28 seconds after the common lock, inside the 720-second window. The historical timings served only to select a runnable workload. [Protocol](PROTOCOL.md) · [Receipts](receipt.json)

## Wall, CPU and memory

Each pair of values gives full original v5 first and compact secant second. Times include both calibration arms.

| Recording | CPU | Launcher wall (s) | Child CPU (s) | Peak child RSS (MiB) | Numerical to published boundary (s) | Common stages through cavity (s) |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0026 | 20 | 368.86 → 88.15 | 308.98 → 82.45 | 1,817 → 1,107 | 314.39 → 81.45 | 216.61 → 81.45 |
| DS26-0146 | 21 | 360.91 → 115.64 | 295.56 → 85.53 | 1,974 → 1,042 | 308.10 → 109.92 | 249.37 → 109.92 |
| DS29-0174 | 22 | 412.57 → 83.28 | 338.04 → 82.42 | 2,021 → 1,130 | 353.11 → 78.38 | 189.77 → 78.38 |
| DS29-0316 | 23 | 408.55 → 131.34 | 364.29 → 100.33 | 2,109 → 1,091 | 357.59 → 120.27 | 259.32 → 120.27 |

Launcher wall includes the method’s normal worker startup and output handling. The original uses the preparation, initial, conservative, family, signed and cavity stages plus its late recovery and final reassociation. Compact publishes at cavity. The common-stage column sums preparation through cavity, excluding the original’s recovery catalogue, which is prepared earlier for late work. These named stage timers start after reading the stored GLRT document. Original late-only logged work took 58.73–163.34 seconds, plot preparation and rendering took 28.59–34.25 seconds, and other child work including startup, packing and validation took 20.98–25.12 seconds. Compact’s outer setup included projector compilation and took 0.08–0.10 seconds. These scopes leave other child work visible in the timing CSV.

Child CPU sums user and system time for the reaped workers. Peak child RSS is the largest recorded Linux process peak in each independent invocation. The timing CSV also contains launcher CPU, launcher RSS, and the original archive byte counts. [Per-stage walls, CPU and resident peaks](timings.csv) · [Paired ratios](summary.json)

Each original and compact run refined three initial branches. The original recorded five refreshes per branch in each arm, for 30 initial refreshes. Compact recorded 15 refreshes in its shared c0 selection. The original workers recorded 3,563–4,181 native backend calls across their production workload. Compact recorded 80–90 position optimizer calls, 544–758 instrumented residual evaluations and 45 compact projections per recording. These are counters at different interfaces. The static inventory records 45 Python function definitions in four listed original files and 37 in five listed compact files, including one C source file on the compact side. The inventory covers the listed orchestration and presentation files, and excludes dependencies outside that list. [Work counts](timings.csv) · [AST file inventory](logic.json)

## Position and conditional RF

Each entry gives c0 first and fitted c second. The two methods published positions 3.56–11.60 metres apart across the eight arms. Conditional RMS is measured on each method’s selected observations.

| Recording | Original error (km) | Compact error (km) | Original RMS (Hz) | Compact RMS (Hz) |
|---|---:|---:|---:|---:|
| DS26-0026 | 1.630 / 1.560 | 1.622 / 1.551 | 83.45 / 82.74 | 72.22 / 72.08 |
| DS26-0146 | 0.627 / 0.548 | 0.624 / 0.545 | 91.95 / 88.58 | 57.51 / 57.50 |
| DS29-0174 | 0.885 / 0.917 | 0.886 / 0.918 | 123.19 / 105.21 | 95.40 / 95.52 |
| DS29-0316 | 1.007 / 1.011 | 1.006 / 1.010 | 131.64 / 133.02 | 107.03 / 107.03 |

The four pairs cover the predeclared runtime strata. Geographic qualification across the full roof corpus remains in the separate 135-recording study. [Per-arm scores and exact legacy checks](scores.csv) · [Full-roof comparison](../../recovery/full-receivers/README.md)
