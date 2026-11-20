# Exact preparation from stored GLRT and causal TLEs

The installed receiver profiles pointed to two costs before localization. Repeated polynomial degree choices were the largest measured numerical operation inside Graph preparation. Character-by-character TLE checksum validation dominated the full native-input profile. The optimized path computes one support geometry per polynomial choice and uses a byte lookup table for standard ASCII TLE checksums. The two changes preserve the original polynomial solver and all checksum checks. [Protocol](PROTOCOL.md) · [Frozen inputs and source](source-lock.json)

| Instrumented installed profile | Track CPU | Polynomial choice CPU | Path recurrence CPU | Element checksums CPU |
| --- | ---: | ---: | ---: | ---: |
| DS29-0082 | 2.95 s | 1.03 s | 0.20 s | 46.73 s |
| DS29-0247 | 8.48 s | 3.71 s | 0.67 s | 37.01 s |

The pilot profiles used the installed compact receiver and complete stored GLRT from the two recordings. Instrumentation added per-call overhead, especially to the checksum generator. The matched service measurements use aggregate timers and consistent diagnostic hashing. [DS29-0082 profile](profile-DS29-0082.json) · [DS29-0247 profile](profile-DS29-0247.json)

The polynomial code gathers the same ordered measurements and applies the same alias lift. It evaluates unique timestamps, support span, clustering, normalized coordinates and the degree penalty once per support. Every eligible degree still calls the original Legendre least squares and the original slope gate. Strict cost improvement preserves the original winner on a tie. The causal validation port computes the same sum over the first 68 columns. Each unsigned digit contributes its value, each minus sign contributes one, and all other ASCII bytes contribute zero. Non-ASCII inputs use the original validation function. [Preparation source](../../../../tools/pipeline_eval/variants/track_preparation.py) · [Component tests](../../../../tests/pipeline_eval/test_track_preparation.py)

The optimized arithmetic replaces two operations and adds zero compiled files or dependencies. The bytewise checksum has four function lines and a lookup-table declaration. The installed checksum spans 15 lines. The shared polynomial chooser spans 41 lines. Its three corresponding installed helper functions span 39 lines and remain available to the original callers. The shared chooser moves common computations out of the degree loop.

## Run the optional preparation

The command uses the installed verified phase release, authenticates the complete native request and its causal snapshots, and emits the existing paired position result. The default backend uses installed preparation. Add `--backend shared` to run both exact changes. The optional `--interior-guard` applies the same paired 20 m rule. [Example truth-free request](example-request.json)

```sh
.venv/bin/python -m tools.pipeline_eval.variants.track_preparation \
  --receiver /path/to/verified/phase-release \
  --request reports/2026_11_19_receiver_screening/original-schedule/track-preparation/example-request.json \
  --request-sha256 f6a220d98b284bb296bc21d25a308d075a3f1d2e3cae942c2245147da4d8fe5f \
  --backend shared --timeout 180
```

## Measured preparation and complete service

The primary comparison ran eight services on CPUs 14 and 15, each with one numerical thread, 512 MiB charged memory, zero swap and 180 seconds. Three primary pairs completed with an exact preparation and position match. The primary installed service on the shifted DS26-0102 offer timed out after 88.15 CPU-seconds. Its shared run completed and withheld both arms. A separately recorded installed completion check used the same input, CPU and limits, and matched the shared tracks, causal evidence, position diagnostics and decision exactly. The primary timeout remains in the charts and resource data. [Prediction seal](prediction-lock.json) · [Parity](parity.json) · [Completion check](completion-check.json)

| Saved input | Polynomial-choice CPU | Track-preparation CPU | Complete native-preparation CPU | Full service CPU |
| --- | ---: | ---: | ---: | ---: |
| DS26-0014 | 1.005 → 0.854 s | 2.36 → 2.23 s | 13.61 → 11.12 s | 61.50 → 61.21 s |
| DS29-0127 | 0.721 → 0.498 s | 1.83 → 1.47 s | 17.84 → 13.26 s | 63.11 → 45.72 s |
| DS29-0247 | 1.802 → 1.286 s | 4.28 → 3.50 s | 18.70 → 14.11 s | 96.89 → 93.35 s |
| DS26-0102, completion check | 1.888 → 1.937 s | 3.85 → 4.18 s | 19.69 → 18.20 s | 88.08 → 86.66 s |

Complete native preparation used 18–26% less CPU across the three completed primary pairs. The larger share came from causal processing. The checksum lookup also runs when the solver validates causal elements later in the same worker. Full service clocks include that work, downstream fitting and host load. Stage clocks and elapsed service wall are available separately. Peak charged memory across the recorded services was 301.1–366.4 MiB. [Stage chart](stage.pdf) · [Primary timing and work counts](stage.csv) · [Complete terminal receipts](resources.json)

The four completed comparisons had identical ordered observations and tracks, ownership, curvature masks, rejected polynomial choice counts, causal history and forecast digests, and paired publication. The shared workers validated 3,534,412 checksums with zero non-ASCII fallbacks. The three original offers published both calibrations. The shifted offer withheld both and kept its forced diagnostic positions. [Zero-c roof chart](charts/c0/track-preparation-roof.png) · [Fitted-c roof chart](charts/fitted_c/track-preparation-roof.png) · [Shifted-offer chart](charts/c0/track-preparation-shifted.png)

| Saved input | Error, zero / fitted c | Conditional Doppler RMS, zero / fitted c |
| --- | ---: | ---: |
| DS26-0014 | 3.396 / 3.404 km | 90.537 / 90.648 Hz |
| DS29-0127 | 0.633 / 0.579 km | 69.760 / 69.738 Hz |
| DS29-0247 | 1.320 / 1.458 km | 60.751 / 60.633 Hz |
| DS26-0102, withheld | 2.038 / 2.023 km forced | 64.693 / 64.779 Hz |

Geographic and frequency results are separate. The original four v5 options appear in the matched original-offer roof charts. [Geographic and frequency data](scores.csv)
