# Exact scalar record materialization on the DS30-0016 positive fix

The candidate saved **54.5 ms of preparation CPU** by eliminating a temporary catalogue for every distinct SGP4 record. Whole saved process time moved from **4.327 to 4.306 s elapsed** and **4.325 to 4.274 CPU s**. This is a small exact preparation improvement. The main preparation cost remains. Both modes reproduced the original signed fix, both calibration arms, regional decision and all eight figures. [Frozen protocol](scalar-causal-elements-protocol.md) · [Profile and process receipts](measurements/scalar-causal-elements-0016.json.gz)

## Preparation costs

Call tracing ran once on the previously sealed mixed handoff with the same verified native RGBA path used in the final pair. The traced preparation took **3.350 CPU s**, compared with **1.636 CPU s** in the separate minimally observed same-session control. The table identifies ownership of the work within the trace. Call tracing inflates Python bookkeeping disproportionately, so the entries do not form an uninstrumented speedup budget. [Earlier phase census](positive-fix-census.md)

| Traced scope | CPU s | Calls |
| --- | ---: | ---: |
| Initial sky, inclusive | 2.038 | 1 |
| Causal catalogue within initial sky, inclusive | 1.400 | 1 |
| Installed parser, across initial sky and history | 1.366 | 99 |
| Per-record SGP4 and epoch cache materialization within the parser | 0.926 | 223,913 |
| Scalar epoch method within materialization | 0.147 | 92,697 |
| Initial ECEF state banks | 0.319 | 2 |
| Phase history, inclusive of parsing | 0.724 | 1 |
| Phase forecast | 0.424 | 1 |
| Prepare tracks from the complete native factors | 0.095 | 1 |

The frames and states retain the exact installed graph and regional calculations. The parser already validates native TLE rows and shares SGP4 records by exact line pair. Only **20** catalogue bodies needed strict native validation. The older canonical TLE export cache and prior catalogue cache already run. The earlier trajectory setup audit established a weak-repeat estimate of **0.064 s** for exact orbit work, and the cross-recording TLE parser study priced about **0.077 CPU s** from prior textual body reuse. This experiment changes creation of a new record, before those existing orbit and export paths. [Earlier exact orbit setup](live-orbit-setup-audit.md) · [TLE parser ceiling](tle-source-cache-ceiling.md) · [Existing element and export cache](../single-core-2x/solver-orbit-table.md)

## Verified change and cost

The source-pinned opt-in computes the identical epoch expression directly from each newly constructed SGP4 record, preserving its float operation order and integer rounding. It charges the same memory accounting, with fixed two- and three-tuple header sizes computed once. Original constructors, strict validation, record keys and cache lifetimes, archive reads, native graph, forecast and region all remain active. A different installed source or nonaccelerated SGP4 retains the original materializer. [Opt-in](scalar_causal_elements.py)

| Scope | Ordinary CPU / elapsed, s | Scalar CPU / elapsed, s |
| --- | ---: | ---: |
| Preparation | 1.636 / 1.637 | 1.582 / 1.582 |
| Full inclusive solve CPU | 2.515 | 2.449 |
| Decision through completed publication | 3.817 / 3.817 | 3.758 / 3.759 |
| Fresh saved process through exit | **4.325 / 4.327** | **4.274 / 4.306** |

The scalar process ran first. Both fresh processes had zero input blocks and major faults. The observed change is 3.3% of preparation CPU and 0.5% of complete elapsed time on this one pair. Recurring process variation remains part of that whole comparison. No broader throughput or original-I/Q change is inferred.

The profile and both timed processes reproduced the original terminal digest, fixed-zero and fitted coordinates, RF RMS of **121.526 / 120.291 Hz**, 116 owner and role rows per arm, the **24-probe** positive regional verdict, the numerical path and paired 179-point grid, and all eight encoded PNGs and decoded RGBA arrays. Both original signed calibrations and the identical native PNG verification were paid. No original waveform data was read. Twenty-five component and adjacent tests passed, including exact epoch values, cache hits, budget fallback and the original parser's error translation.

To reproduce, run `active_preparation_trial.py profile NEW_TMPFS_ROOT` followed by `active_preparation_trial.py pair NEW_TMPFS_ROOT` in the ordinary pinned release environment. Use the shared Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread. The launch binds the previous authenticated raw packet and the complete saved positive-fix inputs and native PNG binary, and each new publication uses its own fresh tmpfs directory. [Trial driver](active_preparation_trial.py) · [Component tests](../../../tests/pipeline_eval/test_scalar_causal_elements.py)
