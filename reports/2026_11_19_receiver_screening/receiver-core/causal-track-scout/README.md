# Causal pilot-start proposals from prior wide winners

A small per-lane tracker proposed start times for 37,673 of 104,162 valid receiver probes over eight saved recordings. On 2,877 capture-era winning families missed by unchanged four-start wide, its proposals landed within two samples for 95 targets and within 20 samples for 462. Among the 563 missed targets with both a proposal and a matched time-shift control, the two-sample count was 59 versus zero. The measured support is for a selective hint. Most probes required the original scout fallback. [Frozen proposals](prediction-lock.json) · [Additional two controls](stride-prediction-lock.json) · [Stage figure](causal-track-scout.png)

## Causal boundary

The tracker receives the probe's exact sample counter and physical receiver/channel/RF/edge lane before seeing that probe's candidates. It emits starts for both receivers before reading either candidate list. It then ingests that probe's gated winner, if any. The tracklet state uses at most two points per hypothesis, known sample-counter phase, 50 ppm drift, and folded CFO compatibility. It has room for eight tracklets per lane and up to four distinct centers per proposal. No Graph membership, orbit, location or future data enter the state. The tracker uses the linear epoch model without a Doppler correction to the forecast. [Protocol](PROTOCOL.md) · [Source and input lock](source-lock.json)

The probe forecast is open loop with respect to the intervention. Feedback before each proposal comes from earlier unchanged wide outputs. A detector using the hints in a new closed loop would have to feed its own past results. The current study consumes stored factors and measures epoch support. Raw detection, position accuracy and elapsed receiver throughput have separate boundaries.

## Missed pilots and regular wide positives

Each row counts candidate families in the recorded native files. A missed family is a capture-era gated winner with no gated wide counterpart within two samples and 1 kHz after alias wrapping. The narrower no-positive subset contains probes where wide had no gated winner at all. These times are compared to sealed start proposals, so a near hit is a potential search location. [Per-probe targets joined after the seal](targets-after-seal.jsonl.gz) · [Exact per-case scores](scores.csv)

| Recording | Any start / all probes | Wide positives, within 1 / 2 / 20 samples | Capture families missed by wide | On missed families, any start | On missed families, within 1 / 2 / 20 samples |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 3,975 / 13,530 | 513 / 596 / 1,159 | 311 | 73 | 6 / 8 / 41 |
| DS29-0082 | 1,996 / 9,736 | 204 / 241 / 651 | 296 | 78 | 7 / 10 / 42 |
| DS26-0237 | 4,563 / 13,532 | 525 / 601 / 1,330 | 377 | 114 | 10 / 13 / 70 |
| DS29-0174 | 4,739 / 13,408 | 517 / 587 / 1,364 | 337 | 106 | 6 / 13 / 62 |
| DS26-0122 | 5,632 / 13,542 | 519 / 628 / 1,731 | 459 | 125 | 11 / 13 / 72 |
| DS29-0247 | 5,809 / 13,534 | 662 / 778 / 1,787 | 339 | 98 | 10 / 10 / 46 |
| DS26-0162 | 5,946 / 13,426 | 779 / 899 / 1,710 | 396 | 137 | 16 / 19 / 78 |
| DS29-0519 | 5,013 / 13,454 | 741 / 850 / 1,518 | 362 | 95 | 5 / 9 / 51 |

The original six account for 67/2,119 missed-family targets within two samples and 333/2,119 within 20. The two independently authenticated full-stride controls add 28/758 and 129/758. Among the 2,375 capture-era positives with no accepted wide candidate, 74 fell within two samples and 388 within 20. On the 222 weak missed capture targets with margin below 0.1, the tracker put zero targets within two samples and one within 20. [Numerical lock](score-lock.json)

| Target group | All targets | At least one proposal | Within two samples | Within 20 samples | Paired two-sample hits, causal / shifted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Wide winners | 34,123 | 13,582 | 5,180 | 11,250 | 5,167 / 4 of 13,527 |
| Capture-era winners | 32,909 | 12,975 | 4,986 | 10,656 | 4,962 / 3 of 12,881 |
| Capture-era winning family missed by wide | 2,877 | 826 | 95 | 462 | 59 / 0 of 563 |
| Capture-era positive with no wide positive | 2,375 | 614 | 74 | 388 | 43 / 1 of 386 |

The null shifts targets within the same receiver lane, strength stratum and 30 second block among probes with a causal proposal. Singleton strata retain their actual targets outside the paired comparison. This difference matters for sparse missed-family strata. On earlier held raw diagnostics, actual four-start centers were available for 13 wide positives and 11 capture positives on the two development recordings. The authentic four-start centers landed within two samples on every one. The causal starts hit two wide positives and one capture positive on the same bounded subset. It contained no capture family missed by wide. Full recordings do not carry the original per-probe center telemetry. [Archived four-start witness](../cfo-stride/prediction-lock.json) · [Per-condition support counts](scores.json)

## Stage cost

The eight streams had 104,162 valid RX probes and 2,092 acquisition exclusions. The tracker saw 16 physical lanes per recording and held up to five tracklets in a lane. It emitted at most three centers in this experiment. Proposals took 0.200 s of process CPU across all probes, and measuring and updating the winner took another 0.315 s, about 4.94 µs combined per valid RX probe on this x86 host. The measurement starts from already decoded native factor documents and includes no detector calls. The authenticated whole-track oracle remained an optimistic comparison because it uses track groups inferred over the complete recording. [Stage times](timing.json) · [Held extension times](stride-timing.json) · [Prior Graph-conditioned experiment](../track-timing/PROTOCOL.md)
