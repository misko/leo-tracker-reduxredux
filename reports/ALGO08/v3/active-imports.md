# Fresh active imports on the weak saved fit

Deferring the installed scanner's detector import cut one complete saved DS30-0016 publication from **5.388 to 5.289 s elapsed** and **5.383 to 5.287 CPU s**, through fresh process exit. Both calibration arms, all 116 owner and role rows per arm, the terminal, numerical path and grid, and all eight official PNG bytes and decoded RGBA digests matched. [Frozen protocol](active-imports-protocol.md) · [Trace and paired receipt](measurements/active-imports-DS30-0016.json.gz)

| Fresh saved process | CPU through exit | Elapsed through exit |
| --- | ---: | ---: |
| Original uninstrumented | 5.383472 s | 5.388252 s |
| Original import census | 5.391111 s | 5.392924 s |
| Deferred detector, uninstrumented | 5.287462 s | 5.288965 s |

The primary pair is the two uninstrumented runs. Both recorded zero dependency input blocks and major faults. Numerical and rendering clocks differed across launches, so the single whole-process pair measures the combined practical effect. CPU outside the measured numerical and rendering stages fell from 1.578 to 1.413 s. The earlier scoped weak execution attributed 0.927 CPU s to new imports before and after those stages. [Earlier stage census](saved-overhead.md)

## Exclusive import census

The diagnostic attributed **0.978 CPU s** to 1,377 first-load modules outside solving and rendering. Another 14.54 ms first-loaded during the solve and 1.75 ms during rendering. Each import's exclusive clock subtracts its direct child loads. The scanner's historical receiver benchmark subtree accounted for **176.73 ms** by summing its modules once. The receiver module itself used 1.53 ms exclusive, while `differential_pilot` used 53.91 ms exclusive and the first SciPy signal subtree used 41.60 ms inclusive. The installed position module loaded its own 504.45 ms subtree before the scanner import. That route remains active, including SciPy stats and Matplotlib.

The source-file loader compiled 154 modules outside solve and rendering, taking 111.43 CPU ms. It compiled another 17 during solving. Across these phases, 135 installed payload module compiles cost 99.30 ms and 36 research module compiles cost 24.91 ms. These clocks sit inside the import totals. They give the measured compile-only ceiling before any bytecode checks or lookup cost. The earlier compatible checked-bytecode study measured 71 ms median CPU saving at its import-only actual-miss boundary. This trial selected the larger observed avoidable dependency and left bytecode alone. [Earlier checked bytecode trial](../single-core-2x/receiver-bytecode-startup.md)

## Deferred import and fallback

The optional `--lazy-scanner-detector` switch applies only to the active publication context. It checks the installed scanner and receiver source hashes and the resolved scanner path and loader, then moves the scanner's one `detector` import to first detector use. Its original scanner body, source checks, numerical solver, rendering, and publication remain active. An unavailable eligible loader or source shape uses the normal importer. A real detector call loads and invokes the original detector with its original arguments. In the measured authenticated handoff there were zero detector calls. The historical benchmark package, `differential_pilot` and SciPy signal never loaded. [Opt-in source](lazy_scanner_detector.py) · [Fallback and trace tests](../../../tests/pipeline_eval/test_active_imports.py)

Both figure sidecars matched after removing their runtime fields and independently checking their image content pointers. The cumulative implementation still used one authenticated saved handoff, the original causal archive and supplied region, the original track graph, exact numerical evidence and explicit layout. Twelve focused tests passed. No waveform or installation change ran.

Use `active_imports.py TMPFS/trial` in the pinned release environment under the shared Gauss lock, CPU 2, `nice -n15`, `ionice -c2 -n7` and one numerical thread. Run `active_imports.py TMPFS/trial --deferred-only` after the census passes its frozen 50 ms threshold. The archived original and diagnostic came from `b2979e9db`. The subsequently frozen opt-in came from `928024696`. The compressed receipt expands to `55934e0444a538df9795f9345c3c90e0e870d0906c63cc36264f5d1efe1428db`. The scope is one saved physical fix, with raw latency and other recordings unmeasured. [Driver](active_imports.py)
