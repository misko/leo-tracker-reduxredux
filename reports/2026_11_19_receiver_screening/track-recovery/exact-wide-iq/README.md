# Exact wide detector on held complete IQ

The stock wide and exact-kernel wide detectors each replayed the complete saved waveform on two new held recordings. `iq_compare` kept the phase-release receiver, each original blind request, waveform decoder, causal catalogue and offered tile fixed. DS26-0241 ran stock first on cores 16/17. DS29-0357 ran the candidate first on cores 18/19. Each service had an enforced 512 MiB limit, zero swap, and a 450-second deadline. [Protocol](PROTOCOL.md) · [Frozen execution](source-lock.json)

## Held selection and comparison boundary

DS26-0241 had the lowest eligible first-segment manifest SHA-256 in the common DS26 matched roster. DS29-0357 had the lowest in the matched DS29 roster after earlier whole-IQ studies were excluded. The source-lock audit covers earlier full-capture schedules and IQ-backed position reports. These recordings had prior archived v5 positions and stored-factor references. They were held from the earlier full saved-IQ benchmark rosters. Selection used recording metadata and SHA-256 only. [Searched rosters, eligible ordering and exact hashes](selection.json)

The native comparison covers every chronological visit, including invalid visits, both receiver probe arrays and every exported candidate field. It compares canonical bytes, preserving distinctions such as signed zero. A separate whole-document check removes only the detector binary hash and the two derived analysis/run identifiers. Clocks, exclusions, policy decisions and support stay inside that comparison. The full position comparison omits only stage durations. The original four v5 options use their capture-era observations and are shown for context. [Exactness audit](native-parity.json)

The 20 ms test reports physical call wall and process CPU independently. Each sampled call is a valid 20 ms dual-receiver IQ window with its chronological visit and lane IDs. Saved-IQ decoding, assembly and the full solve have separate time measurements. These host replays measure processing of the recorded workload. [Per-call timings](native-call-times.jsonl.gz) · [Complete stage and service timings](complete-comparison.csv)

## Held replay results

The stock and candidate outputs were byte-identical across all **13,547 chronological visits**, including 33 invalid visits. Both full unmodified scientific result envelopes, down to the coordinates, conditional frequency scores, RF RMS and work counters, were exact in both calibration arms. All four services completed under the enforced 512 MiB limit, with zero swap and no OOM. [Exactness audit](native-parity.json) · [Both-arm charts](charts/index.html)

| Recording | Valid detector calls per mode | Call wall P50 ms, stock → candidate | Call wall P95 ms | Call wall P99 ms | Actual wall ≤20 ms | Actual CPU ≤20 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0241 | 6,753 | 24.41 → 24.48 | 33.22 → 33.03 | 58.71 → 49.63 | 650 → 319 | 727 → 372 |
| DS29-0357 | 6,761 | 24.58 → 23.54 | 32.49 → 30.75 | 49.53 → 42.19 | 241 → 900 | 273 → 945 |

| Recording | Detector CPU s, stock → candidate | Raw stage wall s | Position stage wall s | Complete service wall s | Whole cgroup CPU s |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0241 | 163.02 → 163.27 | 113.35 → 114.75 | 95.46 → 87.42 | 210.10 → 203.40 | 290.69 → 286.68 |
| DS29-0357 | 166.08 → 159.01 | 118.29 → 109.92 | 91.50 → 98.38 | 210.96 → 209.69 | 293.57 → 291.31 |

The per-call P95 and P99 improved on both recordings. DS26 detector CPU was essentially unchanged, while DS29 detector CPU fell 4.3%. Most valid calls exceeded 20 ms on both recordings. There is one timing per mode and recording. The unchanged fit stage took different amounts of time between runs, so the whole-service differences do not isolate a detector speedup.

Absolute position errors in `c = 0`/fitted-`c` order were 0.820/0.872 km on DS26 and 0.530/0.570 km on DS29 for both wide detectors. The corresponding archived no-repair v5 errors were 0.594/0.678 and 0.439/0.440 km on capture-era observations. Conditional RMS and the historical RF values remain separate in the score table. [Scores including all four original v5 policies](scores.csv)

## Reproduce the scores

The position outputs were sealed before the scorer opened the geographic references. The archived as-measured package retains the preregistration and raw supervisor bytes. The detector source study retains the exact native build, verified here by the loaded stock and candidate SHA-256. [Native release](native-release.json) · [Build receipt](native-build-receipt.json) · [Source archive](as-measured-source.tar.gz)

```sh
python -m tools.pipeline_eval.qualification.exact_wide_iq_results score \
  reports/2026_11_19_receiver_screening/track-recovery/exact-wide-iq --out /local/score
```
