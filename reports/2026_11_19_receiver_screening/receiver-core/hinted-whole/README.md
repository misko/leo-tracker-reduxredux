# Causal GLRT hint feedback on complete saved IQ

This paired study runs the same wide detector family and phase-release solver on DS26-0237 and the additional DS29-0519. Both arms read the entire saved recording in one chronological lane. The selector uses its own earlier detected winners. Each receiver's proposal is committed before either receiver is analyzed on the new visit. Stock runs the same scout in shadow. Both modes preserve the detector gate and the four-center budget. The hinted native ABI may replace slot four with only the first proposal. Neither capture-era peaks nor future Graph or position outputs are available to the selector.

The raw archive, decoder release, valid sample counters, delivery clocks, exclusions and cutoff are verified with the original capture adapter. Both detector outputs enter the same private winning-probe handoff and unchanged phase-release preparation. Matching position inputs retain the original causal catalogue, 25 km offer and both calibration arms. The published original four v5 references are on capture-era factors. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json)

There is one fresh worker per mode per recording, with the order reversed across the two cores. Each complete replay uses an enforced 512 MiB cgroup, zero swap, nice 10 and a 450-second service deadline. Detector CPU covers the ABI and native result decoding on valid windows. Scout CPU is measured independently. Raw wall includes decoding saved IQ. Complete wall includes the handoff and both position calibrations. No new IQ collection occurred.

## Recorded-IQ results

All four workers completed both calibrations under the deadline, with 512 MiB peak cgroup charge and zero swap. The two fresh stocks reproduce the independent full-stride controls byte for byte at the native handoff, including both position arms, RF values, all non-timing metrics and the same causal catalogue. [Independent stock verification](independent-stock.json)

| Recording | Valid visits | Hinted lanes proposed | Actual replacements | Gate-positive lanes, stock → hinted | Detector CPU s | Scout CPU s | Complete wall s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0237 | 6,766 | 4,575 | 3,936 | 4,008 → 4,037 | 102.33 → 101.88 | 0.899 → 0.889 | 182.24 → 173.44 |
| DS29-0519 | 6,727 | 5,040 | 4,136 | 4,768 → 4,787 | 145.20 → 165.17 | 0.945 → 1.057 | 254.18 → 280.57 |

The underlying sample support, valid visit counts and exclusions matched for both paired recordings. The complete raw-lane clocks were 129.42→126.89 s and 176.90→203.30 s. The study has one timing per mode and recording. [Resource measurements](resources.csv) · [Native slot trace](trace.jsonl.gz)

The retrospective detector score opened capture-era winners after sealing these predictions. Join keys are visit, receiver, exact sample counter, channel and actual RF. Agreement requires an accepted candidate within ±2 circular epoch samples and 1,000 Hz of folded CFO. On DS26 the hinted detector recovered 17 capture-era winners that were absent from every stock gated alternative and lost 4 previously available. On DS29 it recovered 9 and lost 8. All 26 gains occurred on visits and receivers where the slot actually changed. Graph-winning agreement rose from 3,326 to 3,340 and from 4,226 to 4,229, respectively. [Sealed detector comparison](detector-scores.json)

| Recording | Calibration | Stock position error km | Hinted position error km | Conditional RF RMS Hz, stock → hinted |
| --- | --- | ---: | ---: | ---: |
| DS26-0237 | `c = 0` | 0.382 | 0.481 | 92.538 → 92.606 |
| DS26-0237 | Fitted `c` | 0.323 | 0.398 | 92.427 → 92.526 |
| DS29-0519 | `c = 0` | 0.334 | 0.378 | 90.230 → 91.073 |
| DS29-0519 | Fitted `c` | 0.324 | 0.342 | 90.341 → 91.170 |

The feedback intervention recovered some detector evidence while geographic error and conditional RF RMS increased in each measured position arm. Both recordings remained within 0.5 km under both modes. [Both-arm charts](charts/index.html) · [Position and frequency scores](scores.csv)

The artifact seal includes the as-measured source with its pre-formatting bytes and the separate ABI and scout ownership checks. The published position and resource tables can be regenerated without reading IQ or archived detector factors.

```sh
python -m tools.pipeline_eval.qualification.hinted_whole_results score \
  reports/2026_11_19_receiver_screening/receiver-core/hinted-whole --out /local/score
```
