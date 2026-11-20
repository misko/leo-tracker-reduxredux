# Wave8 ordinary GLRT CPU and input preparation

Retaining the prepared CI16 buffers cut median warm x86 visit wall from **27.84 to 23.71 ms** on the authenticated local mmap path. The 20 ms target passed on **8/60** candidate calls and **1/60** original calls. Each call runs both physical receivers. Timing begins at the warm local saved-CI16 read and ends after Python has received native candidate fields. Archive decompression, receiver setup, hardware acquisition and positioning sit outside that clock.

| Read path | Median original → reusable | p90 original → reusable | Within 20 ms original → reusable |
| --- | ---: | ---: | ---: |
| Warm mmap + SHA-256 | 27.84 → 23.71 ms | 31.62 → 27.89 ms | 1/60 → 8/60 |
| Warm `fromfile` + SHA-256 | 29.54 → 24.18 ms | 33.02 → 28.69 ms | 0/60 → 6/60 |

These are five alternating pairs per read path across 12 held valid visits, with eight from DS26-0036 and four from DS29-0082. Four original capture-validity exclusions remain in the roster. The profiler's disjoint outer C stages account for 1,567.35 of 1,569.38 ms of original mmap detector CPU over 60 calls. Its nested search clocks distinguish elapsed acquisition from the fine FFT included within it. The proposal fold, correlation and ranking timers are also nested.

| Exclusive CPU contribution across 60 mmap visits | Original | Reusable preparation |
| --- | ---: | ---: |
| Fractional epoch | 559.82 ms | 559.98 ms |
| CI16 preparation + cleanup | 372.96 ms | 171.30 ms |
| Fine FFT | 205.54 ms | 179.31 ms |
| Integer GLRT | 149.95 ms | 151.19 ms |
| Proposal | 130.91 ms | 128.65 ms |
| Coarse | 110.64 ms | 108.22 ms |
| Conditioned fallback | 32.59 ms | 28.85 ms |
| Other measured and residual | 6.97 ms | 6.78 ms |
| All detector CPU | 1,569.38 ms | 1,334.29 ms |

The largest remaining kernel is fractional epoch, now 42% of candidate detector CPU. The largest outer non-search stage was CI16 preparation and cleanup. The isolated modification preserves all preparation arithmetic and refreshes every raw, normalized and prefix sample on each visit. It reuses the already allocated 12.8 MB dual-RX preparation arrays within the detector context. The initial visit still allocates and faults those pages. A separate one-context C process on the first archived visit of each case peaked at 41,168 → 41,100 KiB for DS26 and 41,448 → 41,352 KiB for DS29. The larger Python runner RSS in the qualification JSON includes archive handling and two concurrent contexts.

Every native canonical payload matched its archived original across all held calls and six synthetic controls, including both weak-planted lanes and zero positive publications for empty or Gaussian controls. The stage timing views end at the detector. Retained preparation fell short of the host deadline.

## Position after partial GLRT replay

Two fresh native clock and offset workers used the verified 12 replacement visits and the remaining ordinary archive. The candidate and complete ordinary control matched on scientific factor bytes, the Graph observation digest, causal TLE inputs, published and forced coordinates, and the decision in both calibration arms. The composed native documents have their own provenance hashes.

| Recording | Fresh + archived visits | `c = 0` error | Fitted `c` error | `c = 0` / fitted RF RMS |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 8 + 6,757 | 0.654 km | 0.739 km | 232.44 / 209.30 Hz |
| DS29-0082 | 4 + 4,864 | Withheld | Withheld | 260.24 / 214.02 Hz, forced diagnostics |

DS29 withheld for weak held-track support. The fresh solver results establish parity on these partial replays. The short-visit CPU clocks exclude the rest of the capture and the solver.

The detector qualification entry point is `python -m tools.pipeline_eval.qualification.ordinary_prepared_eval`, with `build`, `DS26-0036`, `DS29-0082` and `package` in that order and one shared local `--work` directory. The follow-up `ordinary_prepared_position` qualification accepts that same `--work` and each `--case`. Invoke it once without `--case` to seal the figures. The standard gallery IDs are `ordinary_prepared` and `ordinary_prepared_position`. [Protocol](PROTOCOL.md) · [Detection summary](qualification.json) · [DS26 per-call data](DS26-0036.json.gz) · [DS29 per-call data](DS29-0082.json.gz) · [Position worker receipts](position-receipts.json) · [Evidence seal](prediction-lock.json)
