# Receiver operations and live code audit

The compact v5 cavity paths still run the same frozen Graph preparation and retain six measured scientific stages. Their main differences are the orbital representation, the number of initial assignments brought to a fit, and the work done inside each fit. Independent cold methods use much smaller preparation paths, then perform their own catalogue search and consistency checks.

## Recorded scientific work

Pairs below are DS26-0036 / DS29-0082. These rows use the original capture-era native factors and the matched roof tile. Stock full v5 has 18 logged stages, including the later addition and reassociation path. The compact cavity variants log six. `compact_finish` continues beyond that boundary and logs 15 compact stages, including residual screening, addition, and reassociation. Stage counts reflect instrumentation granularity. All listed v5 paths kept 3,395 / 1,868 winning observations and 94 / 61 Graph tracks on these captures. [Full v5 records](../../2026_11_18_pipeline_eval/predictions/roof16/v5_lean.jsonl.gz) · [Compact finish stock](../../2026_11_19_short_receiver/shared-search/stock-positions.jsonl.gz)

| Compact cavity path | Initial c = 0 branches brought to a fit | Initial phase fits | Optimizer calls | Objective evaluations |
|---|---:|---:|---:|---:|
| Stock compact, reference optimizer | 3 / 3 | 15 / 15 | 100 / 70 | 2,332 / 1,599 |
| First-ranked assignment | 1 / 1 | — | — | — |
| Secant | 3 / 3 | 15 / 15 | 100 / 70 | 650 / 474 |
| Two refreshes | 3 / 3 | 6 / 6 | — | — |
| Secant plus two refreshes | 3 / 3 | 6 / 6 | 42 / 34 | 407 / 333 |
| Screen plus secant, independent CLI smoke | — / 3 | — / 9 | — / 64 | — / 450 |

The first-ranked path still discovers and ranks assignments before fitting the highest-ranked branch. The recorded compact projector count stays at 45 calls on both cases. Secant keeps the stock number of optimizer invocations and changes the work per invocation. The two-refresh policy uses 32 / 24 phase fits across the measured early initial and recovery stages of the combined worker, including 6 / 6 during initial selection. The screening smoke ran two phase fits for each of three candidates and completed the winner with three further phase fits. Its DS29-0082 endpoints and conditional RF RMS matched the previously measured secant run in both arms. [First-ranked receipts](../../2026_11_19_short_receiver/search-budget/v5_first_ranked.jsonl.gz) · [Stock optimizer](../../2026_11_19_receiver_convergence/position-fit/reference-positions.jsonl.gz) · [Secant optimizer](../../2026_11_19_receiver_convergence/position-fit/secant-positions.jsonl.gz) · [Combined worker](../../2026_11_19_receiver_convergence/combined-fit/positions.jsonl.gz) · [Independent screening receipt](screen-cli-smoke.json)

The stock compact worker's retained geometry reached 24.60 / 27.07 MB. The original prepared array model at those largest shapes was 400.48 / 242.57 MB. Those numbers describe geometry storage. The worker also retains observations, tracks, orbit state and solver workspace. [Compact projector receipts](../../2026_11_19_short_receiver/search-budget/orbit_projector.jsonl.gz)

Two identity-preserving changes remove work within the same scientific stages. Shared association executed 16 of 28 logical requests in each completed primary pair and reused 12. It reduced profiled candidate-time cells from 99,767,136 to 16,861,180 on DS26-0036 and from 47,087,040 to 8,001,995 on DS29-0082. The original DS26 exploratory initial profile recorded 12 `explore` calls, 28 `association` calls, 1,652 `curve` calls, three `refreshed` calls and 15 `bounded_gauss_newton` calls. That profile retains its top 80 entries. Endpoint reuse cut native bound likelihood solves from 211 to 65 and from 143 to 45. These counters describe different operations. [Shared association receipts](../../2026_11_19_short_receiver/shared-search/receipt.json) · [Stock initial profile](../../2026_11_19_short_receiver/shared-search/stock-initial-profile.json.gz) · [Native endpoint counters](../../2026_11_19_receiver_convergence/likelihood/native-counters.json)

## Bounded live traces

The trace used the first complete captured visits through 32 s of DS26-0036 on the original sample counter. It retained 722 scheduled visits with 1,440 valid receiver probes and a 31.966 s sample span. The temporary derived native document occupied 2,378,238 bytes. Its parent native and tracker-config digests and its derived digest are in the trace receipt. Live counts include calls and executed lines in the pinned `leo` source and `tools/pipeline_eval` during each operation. A named function is counted by source file and line. Generated functions such as comprehensions contribute their executed lines. The trace covers project Python after imports and before archive publication. [Trace script](trace_boundaries.py) · [Exact trace receipt](trace-boundaries.json)

| GLRT preparation boundary | Named functions | Named calls | Executed lines | Source files hit | Materialized output |
|---|---:|---:|---:|---:|---|
| Stock native JSON through frozen Graph | 27 | 14,352 | 493 | 8 | 311 winners, 9 tracks holding 246 points |
| Streamed native JSON through same Graph | 38 | 66,612 | 543 | 7 | Same winners, track IDs, times, CFOs and curvature indexes |
| Cold point-pair extraction | 3 | 4,394 | 59 | 1 | 16 pairs from 819 eligible pairs |
| Cold rate-triplet extraction | 6 | 2,621 | 106 | 1 | 9 tracklets |
| Cold joint-pass extraction | 7 | 2,638 | 136 | 2 | 9 tracklets |

The streamed parser narrows individual GLRT records and clears its private source document after building Graph. It visits more Python code and calls the original Graph implementation. The three cold candidate builders directly consume the same retained probes and apply their own candidate linking and summarization rules.

The projection trace separately fed the original NumPy projector and the C projector the same deterministic bank of 32 satellites, 17 knots, 160 observation times, per-satellite phases and three evaluation sites. Frequency, elevation and phase derivative matched the reference at absolute tolerances of 1e-5 Hz, 1e-8 deg and 1e-5 Hz/s. Prepared array sizes count retained data arrays. [Trace receipt](trace-boundaries.json)

| Orbit projection | Named Python functions | Named Python calls | Executed Python lines | Source files hit | Retained arrays |
|---|---:|---:|---:|---:|---:|
| Stock NumPy | 6 | 16 | 106 | 4 | 655,360 bytes |
| Compact C | 6 | 14 | 108 | 3 | 273,408 bytes |

The compact fixture made three native kernel entries. The C11 kernel is 2,596 source bytes and compiled to a 15,200-byte x86-64 shared library on the host. It uses the existing Python NumPy/ctypes wrapper and C math library. The stock fixture used the frozen phase-shift, interpolation, and geodetic frame methods. Both kept the Python calls producing the local Earth frame. [Projector kernel](../../../tools/pipeline_eval/variants/orbit_projector.c) · [Projector wrapper](../../../tools/pipeline_eval/variants/orbit_projector.py)

## Downstream dependencies

The stock and modified compact v5 workers share the pinned v5 scientific source, frozen Graph configuration and matched site offer, a causal view of the TLE archive, and the bound native likelihood backend. The rank and optimizer policies retain these dependencies. The C projector adds a host build and load of its small shared object. Shorter preparation and cheaper calls leave the later inference dependencies in place.

The portable compact adapter made this archive requirement explicit. Its exact DS26-0036 parity run used 38 prior collections, 27 distinct snapshot payloads, 1,524 genuine previous-orbit records and 5,765 causal forecast transitions. The native observations and one offered tile are only part of the reproducible input to that receiver. [Portable v5 parity and archive inventory](../portable-v5/README.md)

The Armijo finish route uses the Armijo optimizer inside `compact_finish`. It retains the final addition and reassociation decisions and records whether residual addition was checked. The discovery memory route instead retains one association result during a single exploration before the existing secant cavity worker. Reuse requires the same state, base, point, method and track scope, and the `association_reuse` receipt counts computed and reused calls. Its regular benchmark uses capture-era factors. The separately bound ordinary-factor trials qualify detector transfer. Both routes verify the frozen v5 source tree, including the discovery and scan code. [Armijo finish source lock](../armijo-finish/source-lock.json) · [Working-memory source lock](../working-memory/source-lock.json)

The two ordinary-factor working-memory trials each cut 24 measured exploratory association calls to 12. Peak fitter RSS fell from 1,066,592 to 1,047,156 KiB on DS26-0036 and from 949,188 to 904,008 KiB on DS29-0082. The DS29-0082 capture-era pair saved about 71 MiB at initial fit and its complete fitter peak rose by about 3 MiB. All three pairs reproduced both coordinates and conditional Doppler RMS exactly. [Working-memory measured receipts](../working-memory/README.md)

Raw robust starts with stored GLRT factors, invokes frozen Graph and passes only freshly generated anonymous tracks, the causal TLE and one supplied tile to the robust EM fit. In its capture-era control, Graph assigned 2,867 / 1,526 points; the fit consumed 94 / 59 eligible tracks. That receiver executed 188,462 / 189,635 coarse and 62,920 / 72,085 fine orbit-state evaluations. The fixed-assignment range-rate variant kept those propagation counts on archived anonymous tracks and accepted three refinement steps per calibration arm on both recordings. [Fresh track and robust fit receipts](../../2026_11_19_short_receiver/raw-robust/control-positions.jsonl.gz) · [Range-rate fit receipts](../../2026_11_19_receiver_convergence/track-fit/positions.jsonl.gz)

The global rate-triplet path starts from GLRT plus causal TLE and searches its own site grid. Its full runs generated 28 / 28 tracklets, associated 19 / 17 and withheld both fixes. Joint pass adds the original tile, uses its own CFO/frame tracklets and fits both arms against independently selected identities. It generated 56 / 34 tracklets, selected 41 / 22 and also withheld both fixes. Their receiver paths dispense with the frozen Graph, v5 history, native bound likelihood and cavity code. The smaller preparation traces therefore trade away those dependencies while leaving the independent catalogue search and validation as real work. [Global rate-triplet positions](../../2026_11_19_glrt_cold_start/rate-triplets/global.jsonl.gz) · [Matched joint-pass positions](../../2026_11_19_short_receiver/joint-pass/matched-tile.jsonl.gz)

Reproduce the bounded traces from the repository root with the frozen v5 source first on `PYTHONPATH`.

```sh
taskset -c 6 env PYTHONSAFEPATH=1 \
  PYTHONPATH="/home/mouse9911/.cache/accuracy-repair-20261115/frozen-001/src:$PWD" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -B reports/2026_11_19_receiver_screening/complexity/trace_boundaries.py
```
