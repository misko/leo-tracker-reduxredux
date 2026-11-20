# Saved wide IQ to position through the private winning-probe stream

This option runs the installed wide detector on both complete saved-IQ lanes. It reads their actual visit messages with a bounded merge, then feeds the compact winning-probe stream to the phase-release receiver. The original receiver entry and public native contract retain their existing paths. DS29-0082 also appeared in the earlier stored-factor trial. DS26-0122 is an additional full wide recording for the private handoff.

## Handoff and identity

Each lane delivers ordered visits and terminal receipts for its segments and worker. The merge verifies complete segment inventory, compressed-input receipts, lane affinity, sample counters, original clocks and exclusions. It passes winners and candidate audit counts to the private writer one probe at a time. Original source/probe, raw-IQ, capture-clock, exclusion and decoder identities are verified. The solver starts with the same causal catalogue, offer, track configuration and calibration settings as stock.

The private path hashes the canonical public packet in a second bounded lane pass. This preserves the exact original native SHA-256 without retaining or writing the full candidate document. Lane messages stay as raw service receipts. They are distinct from the much smaller artifact sent into the position worker. No new detector policy, localizer or archive schema is involved.

## Complete replay measurements

All four fresh executions finished with both calibration arms under the enforced 512 MiB limit and zero swap. The private path reproduced the stock projection byte for byte, as well as the stock positions, conditional RF RMS, scores and solver decisions. All 13,542 valid receiver probes and one invalid visit were accounted for on DS26-0122. DS29-0082 kept 9,736 receiver probes and 1,904 invalid visits.

| Recording | Handoff MB, stock → private | Handoff wall s | Handoff CPU s | Assembler high-water MiB | Complete replay wall s | Complete replay CPU s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0122 | 24.54 → 1.30 | 0.90 → 1.07 | 0.89 → 0.79 | 167.6 → 65.1 | 162.69 → 180.27 | 198.66 → 192.99 |
| DS29-0082 | 17.15 → 1.43 | 0.84 → 0.59 | 0.63 → 0.57 | 139.5 → 67.2 | 131.89 → 115.68 | 128.27 → 130.58 |

The handoff files shrank 94.7% and 91.7%. Companion lane logs retained approximately 27.19 and 19.47 MB respectively in each mode. The assembler high-water mark is for its own process through the handoff. Whole-service charge reached the same 512 MiB cap for all four attempts without OOM or swap. Complete replay wall includes decoder, detector, handoff and both-arm solve. Raw and position stage times varied across pairs, so these measurements do not establish a consistent whole-replay speedup.

Paired geographic errors were 1.320/1.318 km on DS26-0122 and 2.489/2.346 km on DS29-0082 in `c = 0`/fitted-`c` order. The archived original v5 references use their capture-era detector factors. [Both-arm charts](charts/index.html) · [Resources](resources.csv) · [Position and conditional RF scores](scores.csv) · [Exact comparisons](parity.json)

## Run the option

Install the checked phase-release intake overlay. Supply its directory to the whole-IQ entry, along with the pinned detector file and two available CPU cores. The path containing the detector must be readable by the existing `leo` replay service account. Place the receiver outputs on a local writeable filesystem.

```sh
python -m tools.pipeline_eval.qualification.winner_stream_trial install /local/receiver
python -m tools.pipeline_eval.qualification.whole_winner run \
  --case DS29-0082 --receiver /local/receiver \
  --detector /path/to/libleo-adaptive-detector.so --detector-sha256 DETECTOR_SHA256 \
  --cpus 3 5 --out /local/new-attempt
```

The first preparatory service stopped before either detector opened the library because its staging directory was private to the parent account. Its terminal receipt and both lane failures are preserved. The measured panel used accessible local ext4 scratch and the same frozen detector, corpus, schedule and resource settings. [Initial launch receipt](initial-launch.json) · [Protocol](PROTOCOL.md)

Supply `--expected-native` to bind a replay to an independently known original native digest. Use `whole_winner recover` with the original attempt directory to reconcile an existing terminal service after loss of its supervisor. The public stock evaluator and its recovery route are unchanged.

The published scorer verifies the receipt and measured-source archive and rebuilds the exact score and resource tables without reading the IQ files.

```sh
python -m tools.pipeline_eval.qualification.whole_winner_results \
  reports/2026_11_19_receiver_screening/receiver-core/whole-winner --out /local/score
```

The comparison measures saved-IQ replay on the host. The original sampling, retune and radio delivery happened before these runs. Decoder and detector timings include the original replay workload. A live-radio wall clock or embedded-board result needs its own measurement.
