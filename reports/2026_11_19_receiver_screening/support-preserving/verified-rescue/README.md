# Do later pilot symbols justify adding a detection?

A second code check passed **1,526 of 1,609** proposed additions across four complete roof recordings. It retained 493/499 (98.8%) of the additions corroborated by the archived capture detector and 1,033/1,110 (93.1%) of the other additions. The original detector is a reference measurement. Its silence leaves open whether an individual pilot was present. [Code evidence on every probe](capture-labels.jsonl.gz) · [Per-recording stage chart](late-symbols.png)

The two-block test used the winning native time and carrier from the differential search without moving either. It compared the known pilot code with a rolled code in two later symbol ranges. Stock-positive packets were kept exactly. For a stock-negative probe, a winning differential packet was added if it passed. A separate control added the same number of donor packets per receiver, tuned channel and band using a fixed hash order. The control measures what changes when choosing a different set of the same size. All four recordings have previously reported position results and share one roof. [Frozen rule and control](PROTOCOL.md) · [Data and timing](stage.csv)

| Recording | Additions passing / proposed | Stock wide | Later-symbol rescue | Count-matched control |
| --- | ---: | ---: | ---: | ---: |
| DS26-0168 | 376 / 401 | 0.805 / 0.796 | 1.472 / 1.473 | 1.505 / 1.506 |
| DS29-0604 | 372 / 401 | 0.735 / 0.734 | 0.724 / 0.736 | 0.769 / 0.789 |
| DS26-0237 | 442 / 461 | 0.382 / 0.323 | 0.479 / 0.428 | 0.325 / 0.313 |
| DS29-0082 | 336 / 346 | 2.489 / 2.346 | 2.146 / 1.947 | 1.524 / 1.815 |

Each pair is horizontal error in kilometres, first with zero calibration and then with fitted calibration. All eight new position services returned both fixes. The rule gave lower error than its count control on the first two recordings and higher error on the other two in both arms. Relative to original no-repair v5 it met both the 5% and 10% allowances on two of four in either calibration setting. Stock reached those allowances on two and three of four with zero calibration and on two of four with fitted calibration. The charts include the four original v5 settings and the unconditional differential detector. [Fitted position errors](charts/fitted_c/late-symbol-rescue-verified.png) · [Zero-calibration errors](charts/c0/late-symbol-rescue-verified.png) · [Count-matched control](charts/fitted_c/late-symbol-rescue-count-control.png)

Conditional Doppler RMS increased relative to stock in both arms on all four recordings. On DS29-0082 it increased from 84.25 to 86.67 Hz with fitted calibration while position error improved by 399 m. On DS26-0168 the same figures went from 70.87 to 83.66 Hz while position error worsened by 677 m. The late-symbol check used a median 2.40 ms of CPU per affected stereo visit, measured on 1,571 visits with a proposed addition. This clock excludes acquisition, the stock and differential searches, and archive I/O. The eight actual position fits used 40.1–107.5 CPU seconds, peaked at 422.8 MiB, and finished with zero swap and OOM kills. [Position and RF scores](scores.csv) · [Per-visit times](verification-costs.jsonl.gz) · [Capped service measurements](resources.csv)

The position rows and plot rebuild from the published receipts. The first command below needs the matching v5 score archive. The second needs only the sealed stage evidence. Re-reading physical waveforms uses the archive reader, the SHA-verified detector logs and a fresh local working directory, followed by the same installed compact solver. All collected samples in this study came from existing recordings. [Matched inputs and service configuration](input-lock.json) · [Sealed prediction inventory](prediction-lock.json)

```sh
python -m tools.pipeline_eval.qualification.verified_rescue_results score
python -m tools.pipeline_eval.qualification.verified_rescue_stage plot
```
