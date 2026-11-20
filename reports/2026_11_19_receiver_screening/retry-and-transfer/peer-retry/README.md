# Eight-anchor measurement of the original peer retry

The eight-anchor retry saved **63.01 ms of paired median detector CPU** on visits that invoked the original 22-anchor retry. It recovered **1 of 3** original rescued probes on outcome-blind visits and **1 of 20** on the separate known-rescue panel. The original retry remains the supported path for preserving its rescued measurements. [Timing and recovery figure](stage.pdf) · [Audit](summary.json) · [Qualification lock](qualification-lock.json)

## Support in the two original primaries

DS26-0237 supplied **448 original rescued receiver-probes with 849 gated retry candidates**. The complete signed conditional and primary-only streams identify both physical primaries for each rescue. The failed primary contributes every completed fractional factor, including its rejected factors. Comparison uses the 13,333-sample cyclic frame and the 227,273 Hz CFO alias period. Matched shuffles permute dual primary outputs within the same RF channel and failed physical receiver over 32 derangements. [Per-candidate support and matched controls](primary-support.csv) · [Source bindings and aggregate counts](primary-support.json)

| Primary proposals | Epoch within two samples | Joint within eight samples and 40 kHz after wrapping CFO | Joint within 32 samples and 80 kHz after wrapping CFO |
|---|---:|---:|---:|
| Failed primary, first rank | 1 / 849 | 0 / 849 | 3 / 849 |
| Passing peer, first rank | 285 / 849 | 118 / 849 | 289 / 849 |
| Failed primary, all completed ranks | 1 / 849 | 2 / 849 | 18 / 849 |
| Passing peer, all completed ranks | 316 / 849 | 130 / 849 | 321 / 849 |
| Both primaries, all completed ranks | 317 / 849 | 132 / 849 | 334 / 849 |
| Both primaries, matched shuffle | 0.27% | 0.18% | 2.16% |

The broad joint window covered at least one original winner on **193 of 448 rescued probes**. Literal CFO differences gave one candidate within that same window. No projected primary proposal satisfied the joint two-sample, 1 kHz alias match. These are measured coverage limits for the stated seed sets and radii. The previous fast four-region partner experiment independently recovered 17 of 49 partner detections using its own seed and verification rules. [Earlier partner-local experiment](../../antenna-confirmation/partner-local/README.md)

An untimed trace captured both primaries’ actual coarse top eight and acquired candidates on the new waveform panel, including incomplete or rejected candidates that the full factor archive omits. Both primary grids together supplied a coarse peak within two samples for **12 of 36** actual gated 22-anchor retry candidates. They supplied a joint eight-sample and wrapped 40 kHz peak for the same count, compared with zero matches in 90 same-recording, same-channel donor comparisons. Thirty-two targets had matched donor visits. The failed-lane raw coarse peaks supplied two of the 36 joint matches, and the passing peer supplied 11. One of the 36 matched a refined acquisition proposal at the tighter two-sample and wrapped 1 kHz criterion. [Raw proposal audit](raw-primary-support.csv) · [Signed attempt and proposal traces](qualification-lock.json)

## Complete detector measurement

The live prototype keeps the original trigger, both 12-anchor primaries and the same eight-candidate budget. Only the failed antenna's conditional retry changes. The retry evaluates the full original CFO-by-epoch lattice with eight evenly spaced anchors drawn from the 22-anchor set and disjoint from its original primary. Fine CFO, integer GLRT and fractional epoch refinement run on that antenna's own samples. The experiment covers 40 hash-selected outcome-blind visits and 20 separate known rescues on DS26-0162, DS26-0237, DS29-0082 and DS29-0519. Three rotating timing repetitions included complete sample-to-factor detection. Original conditional output matched the signed archive on every visit. [Protocol](PROTOCOL.md) · [Input lock](input-lock.json) · [Per-visit equality](visits.csv) · [Timing rows](timing.csv)

| Cohort and measurement | Original conditional | 12 anchors only | Eight-anchor retry |
|---|---:|---:|---:|
| Blind positive probes | 25 | 22 | 23 |
| Blind rescued probes with a one-to-one candidate match | 3 / 3 | 0 / 3 | 1 / 3 |
| Blind rescued candidates matched | 5 / 5 | 0 / 5 | 1 / 5 |
| Known rescues with a one-to-one candidate match | 20 / 20 | 0 / 20 | 1 / 20 |
| Known rescued candidates matched | 31 / 31 | 0 / 31 | 2 / 31 |
| Blind complete detector CPU mean, ms | 291.10 | 256.52 | 280.23 |
| Actual retry visits, complete detector median CPU, ms | 420.94 | 251.55 | 357.18 |
| Actual retry visits, complete detector P95 wall, ms | 496.30 | 281.88 | 413.17 |

The two 12-anchor primary attempts matched in every mode, including rejected public candidates. For each mode, the 120 primary attempts emitted 960 public candidates and 557 complete fractional factors with 118 passing the fractional gate. The 28 original 22-anchor retry attempts emitted 224 public candidates, 135 factors, and 36 fractional gate passes on 23 probes. The 28 eight-anchor attempts emitted 224 public candidates, 111 factors, and three fractional gate passes on two probes. Neither alternative introduced a positive probe or an unmatched positive candidate. Canonical public and factor equality held on 72 of 80 outcome-blind physical probes and 20 of 40 known-rescue probes for each alternative. No timed complete detector call met 20 ms. Each case ran single-threaded on its assigned core with 512 MiB charged memory and zero swap. [Candidate and gate counts by attempt](attempts.csv) · [Per-lane comparison](lanes.csv)

The DS26-0237 known-rescue subset recovered zero of 12 original rescued probes. On the 20 known rescues, an independent schedule assigning the original retry to one in four visits would recover 5.75 probes in expectation. Choosing the five visits with access to the hidden outcomes could recover at most six probes. An independent mixture would require the full retry on approximately 89.5% of this cohort to reach 90% expected retention. These calculations use measured branch outcomes and are untimed diagnostics. The coverage and timing results did not qualify either a scheduled mixture or a complete selector-plus-eight-anchor position replay. [Schedule diagnostic](summary.json)

## Reproduce

Use an unpublished evidence checkout to recreate the selected panels and publish another copy. The freeze step writes its input lock into the evidence directory.

```bash
.venv/bin/python -m tools.pipeline_eval.qualification.peer_retry_support
.venv/bin/python -m tools.pipeline_eval.qualification.peer_retry_trial freeze /var/tmp/peer-retry-repeat
.venv/bin/python -m tools.pipeline_eval.qualification.peer_retry_trial run /var/tmp/peer-retry-repeat DS26-0237 4
.venv/bin/python -m tools.pipeline_eval.qualification.peer_retry_trial run /var/tmp/peer-retry-repeat DS26-0162 4
.venv/bin/python -m tools.pipeline_eval.qualification.peer_retry_trial run /var/tmp/peer-retry-repeat DS29-0082 5
.venv/bin/python -m tools.pipeline_eval.qualification.peer_retry_trial run /var/tmp/peer-retry-repeat DS29-0519 5
.venv/bin/python -m tools.pipeline_eval.qualification.peer_retry_results /var/tmp/peer-retry-repeat
```
