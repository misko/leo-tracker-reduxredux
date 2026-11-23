# Raw diagnostics on two short physical DS30 recordings

DS30-0227 and DS30-0057 are the smallest withheld and complete workloads by issued visits among the 100 archived ALGO08v3 pairs. The unfiltered combined candidate used the installed track graph, native regional likelihood and geographic projection, cold-row reuse and predictive grid phase-state reuse. These are development workload diagnostics using original signed input, region and causal TLE archives. [Frozen cases, order and native pins](short-raw-diagnostic-protocol.md)

The candidate correctly withheld on DS30-0227 and published a two-arm fix and all eight figures on DS30-0057. The installed DS30-0057 run reached its archived position and then timed out during figure publication. This leaves the complete two-case elapsed-time comparison unresolved. [Scored receipt](measurements/short-raw-diagnostic.json)

| Case | Build | Raw pages resident | To detections | To terminal | Complete elapsed | Process CPU |
|---|---|---:|---:|---:|---:|---:|
| DS30-0227 | Installed | 5,090 of 5,090 | 1.068 s | 7.282 s | 13.647 s | 1.288 s |
| DS30-0227 | Candidate | 5,090 of 5,090 | 1.331 s | 12.458 s | 13.767 s | 3.379 s |
| DS30-0057 | Installed | 817,049 of 817,049 | 18.014 s | 39.587 s | Censored at 150 s | 29.881 s through reap |
| DS30-0057 | Candidate | 817,049 of 817,049 | 15.454 s | 42.344 s | 62.519 s | 21.606 s |

The installed DS30-0057 process was blocked in XFS writeback during `fsync` with two PNGs staged. The timeout sent a kill signal at 150 s. Reaping completed at 198.522 s, including time pending in the kernel. The stock detector and terminal hashes match the archived complete publication, whose eight PNGs were independently decoded and verified. The candidate published eight fresh PNGs and a complete 179-point grid. Its regional scorer used the native path in all 25 calls, with 468 cold-row reuses and 356 prepared grid calls. [Fresh handoff and separate archive verification](measurements/short-raw-diagnostic.json)

Both cumulative subsets retain every assigned recording. The one-case paired median and summed elapsed ratios were both 1.009 (candidate divided by installed), above the 0.500 target. Across two cases, the candidate totals 76.286 s and the installed total is at least 163.647 s. The cutoff gives upper bounds of 0.713 on the paired median and 0.466 on the summed ratio. The exact two-case ratios are unobserved. The paired median is the mean of the two ratios, so the DS30-0227 ratio alone puts it above 0.504 even if the other ratio approaches zero. The 0.500 paired median gate is therefore missed. The candidate had zero missed fixes, false fixes, and process failures. [Cumulative timing and outcomes](measurements/short-raw-diagnostic.json)

## Withheld case

On DS30-0227, both arms correctly withheld for `no_active_curvature` without a position or figures. The installed receiver selected zero factors and the candidate selected 13 from the same 28 probes. The candidate’s regional precheck reported that it lacked a disjoint Graph subset and the ordinary inference path reached the same withhold. The precheck took 2.074 CPU s. The complete elapsed times were 13.647 s installed and 13.767 s candidate, with 1.288 and 3.379 CPU s respectively.

## Calibration on DS30-0057

Both builds used their own fixed detector observations, while the zero and fitted calibration arms within each build shared candidates, other priors and search budgets. Horizontal errors use the operator site authority. [Reference audit](../../2026_11_21_ds30_full/reference-audit.json)

| Build | `c = 0` error | Fitted `c` error | `c = 0` RF RMS | Fitted `c` RF RMS |
|---|---:|---:|---:|---:|
| Installed | 0.426 km | 0.525 km | 109.967 Hz | 109.829 Hz |
| Candidate | 0.240 km | 0.297 km | 125.298 Hz | 125.311 Hz |

The candidate reduced horizontal error by 186 m with fixed-zero calibration and 228 m with fitted calibration. RF RMS rose by 15.330 Hz and 15.482 Hz respectively. Fitting `c` raised horizontal error by 98 m on installed v3 and 57 m on the candidate. It lowered RF RMS by 0.139 Hz on installed v3 and raised it by 0.013 Hz on the candidate.

## Reproduction

The pair driver verifies the installed launcher, exact frozen unfiltered entry point and three native libraries. Under a single Gauss lock, each measured arm starts with an empty output, a shared prepared font cache, fully resident raw input and the same CPU and I/O scheduling settings. Raw warming, evidence verification, and scoring against the operator site authority are outside the process clocks. [Driver](short_raw_diagnostic.py)

The first cache check on DS30-0057 found 790,864 of 817,049 pages resident after warming. It stopped before a timed process and preserved the completed DS30-0227 pair. A later exclusive lock acquisition resumed only the two unmeasured DS30-0057 arms. Both passed the full raw-residency check, while charged process input blocks and filesystem waits remained different. No timed arm was repeated. The complete process clocks, logs and hashed libraries are retained in `/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-short-raw-diagnostic-pairs`. One hundred focused component tests passed. [Scorer and censoring logic](short_raw_diagnostic_score.py)
