# Private winning-probe stream for the phase-release receiver

The private stream reduced the uncompressed handoff by **91.7–94.7%** on three full wide-detector recordings. The stock and candidate Graph receipts have identical hashes, covering every selected observation, track, owned point, curvature index and preparation metadata field. Both calibration arms returned identical position, conditional RF RMS and frequency score. The complete stationary receiver still spends most time after Graph. One paired timing per recording showed mixed whole-worker results with the converter measured separately and included.

## What the detector needs to hand off

Graph selects only candidates with `passed_fractional_margin_gate is True`. It maximizes fractional margin, then chooses the lowest candidate rank. An exact tie on both fields keeps the earliest candidate in detector order. The original code also calls `frequency_evidence` first, validating every candidate and counting duplicates by CFO and epoch separation. Those checks and exact duplicate and distinct counts are preserved by the producer. Graph uses the winning CFO, actual RF, receiver and channel, and the sample-counter-derived midpoint and observation identity. The winning margin remains in the observation record. The original lane split and segmentation run unchanged.

Valid negative probes retain support and counts. A missing winner cannot become a Graph point, and the graph time gaps are still derived from sample counters. Clock bracket, time authority, all delivery timestamps, exclusions, original capture metadata and visit/probe counters survive the transport. Candidate alternatives, epoch values after validation, and the full candidate matrix are unnecessary for this specific Graph-to-phase-release boundary. The original stored file and public contracts still serve callers that need all candidates.

## Fresh capped results

Each phase-release worker ran on a pinned core with one numerical thread, nice 10, and an enforced 512 MiB cgroup and zero swap. All six completed without OOM or swap. The console converter was timed separately on the corresponding core, including its process startup. These are stored-detector-to-position measurements. They contain no RF acquisition or new detector replay time.

| Wide recording | Handoff MB, original → private | Read + Graph wall s, original → private | Full solver + converter wall s, original → private | Peak cgroup charge MiB, original → private |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 23.46 → 1.27 | 1.85 → 1.51 | 36.58 → 35.82 | 268.9 → 271.3 |
| DS29-0082 | 17.15 → 1.43 | 0.74 → 0.53 | 19.65 → 20.15 | 283.2 → 260.5 |
| DS29-0247 reserve | 25.23 → 1.33 | 2.02 → 1.72 | 53.43 → 50.70 | 310.2 → 309.7 |

The console converter took 0.19, 0.15 and 0.48 s, respectively. Read plus Graph including the converter was 1.70, 0.68 and 2.20 s. The process high-water RSS through Graph fell 17.5–25.2 MiB, while whole-worker charge peaked later and changed by different amounts. Whole measured CPU including conversion was 35.01→34.36, 19.39→19.86 and 50.64→49.12 s. A shared Graph hash audit took under 0.020 s per worker and was inside both full-solve measurements.

Both arms preserved each paired geographic error as well as the RF fit. Errors in zero-`c`/fitted-`c` order were 1.003/0.935 km, 2.489/2.346 km, and 1.326/1.338 km. The charts also show all four original v5 policies on their archived capture-era detector input. [Both-arm charts](charts/index.html) · [Per-case scores and conditional RF](scores.csv) · [Resource measurements](resources.csv) · [Timing figure](resources.png)

## Probe-by-probe producer

The actual saved `replayed-{0,1}.jsonl` IQ worker messages were merged chronologically and fed directly into `Writer.probe()` one probe at a time, with the original authenticated capture metadata finalized at the end. All 6,769/6,772/6,775 visit times and 4/1,904/8 exclusions were independently verified from the lane messages. Each emitted private stream was byte-identical to conversion from the original authenticated native JSON. The producer receipts bind both lane files, private byte size and private SHA-256. This replay demonstrates the adapter on real detector replies. A live acquisition service integration remains unmeasured. [Producer receipts](producer-receipts.json)

## Reproduce

The optional installer verifies the released phase-release source before adding its private input route. Run the installed program with the existing options, setting `--native` to the private stream, `--native-sha256` to its digest and `--native-origin-sha256` to the original native SHA-256. Omitting the origin flag uses the normal input path.

```sh
python -m tools.pipeline_eval.qualification.winner_stream_trial install /local/receiver
python -m tools.pipeline_eval.qualification.winner_stream_producer \
  /local/native.json OLD_SHA256 /local/native.winners
```

The source lock pins the original full wide cohort, receiver libraries, per-mode files and actual launch source. The companion source archive preserves the measured bytes prior to lint-only formatting. Offline rescoring verifies the evidence and reproduces the comparisons without opening the original factor or IQ files.

```sh
python -m tools.pipeline_eval.qualification.winner_stream_results \
  reports/2026_11_19_receiver_screening/acquisition-support/winner-stream --out /local/score
```
