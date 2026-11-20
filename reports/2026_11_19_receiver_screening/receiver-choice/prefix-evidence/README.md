# Choose the detector from 24 seconds of pilot recurrence

The blind prefix rule selected five timing regions on **6 of 20** recordings. Substituting the selected entire-branch position improved two and worsened four compared with stock in each calibration arm. Median error rose to **0.807 km at zero calibration and 0.850 km with fitted calibration**, compared with 0.774 and 0.776 km for fixed stock. This twenty-case result is a retrospective test of the frozen branch choices. [Stage figure](stage.pdf) · [Entire-branch diagnostic](stage.csv)

| Entire-branch comparison on 20 recordings | Median zero / fitted c, km | Within 10% of original v5, zero / fitted c |
| --- | ---: | ---: |
| Fixed stock | 0.774 / 0.776 | 11 / 11 |
| Fixed fifth | 0.746 / 0.824 | 12 / 12 |
| Frozen prefix choice | 0.807 / 0.850 | 10 / 10 |
| Per-arm, per-recording oracle bound | 0.581 / 0.626 | 13 / 14 |

The rule used a complete 24-second prefix of the authenticated ADC sample-counter clock, expressed in exact integer samples at nominal 10 MS/s. It matched gate-passing pilot epochs and retune-corrected CFO across three successive probes on the same physical receiver, channel and edge. A positive paired recurrence gain had to pass both half-prefix and lane-support gates. An empty, tied or insufficiently supported prefix chose stock. Predicted choices and the original waveform hashes were sealed before using the position scores. [Frozen protocol](PROTOCOL.md) · [Per-recording prefix support](choices.json)

## Actual stock-warmup compact results

| Recording | After 24 s | Stock zero / fitted, km | Fifth zero / fitted, km | Actual prefix zero / fitted, km | Actual compact wall |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0014 | Fifth | 0.472 / 0.755 | 0.855 / 0.907 | 0.734 / 0.968 | 57.36 s |
| DS26-0144 | Fifth | 0.162 / 0.180 | 0.264 / 0.176 | 0.263 / 0.179 | 73.50 s |
| DS29-0491 | Stock | 1.501 / 1.443 | 0.751 / 0.694 | 1.501 / 1.443 | 54.12 s |

Both switched inputs took the first 542 complete visits from stock, then 6,230 and 6,214 visits from the verified fifth-center stream. They changed 6,904 and 6,419 receiver-probe payloads from stock. The DS29-0491 stock fallback reproduced the original stock native bytes and both scientific outputs in a new compact solve. All three runs preserved the existing causal catalogue, tile, original request, installed phase-release code, excluded visits and both calibration arms under 512 MiB and zero swap. The measured boundary begins at immutable detector outputs. The live switched whole-IQ detector boundary remains unmeasured. The fixed controls are existing measured whole-IQ results on the same inputs. [Sealed fit receipts](fit-lock.json) · [Actual per-arm geography and separate RF residuals](actual-scores.csv)

Median CPU for the recurrence decision across the original twenty recordings was **7.46 ms**. The two fresh traces expose the cost of evaluating both native policies during warmup. There were 542 complete dual-RX calls per policy on DS26-0144 and 540 on DS29-0491. The measured fifth calls add **17.29 s and 16.68 s of detector CPU**, respectively, above stock's 12.77 s and 14.44 s. These are sums of native CPU on the archived branch executions. They do not measure the live wall cost of evaluating both policies together. The initial compact launcher and fresh input preparations needed schema adjustments before their services started. A lint-only repeat of the offline prefix scan reproduced all twenty choices and evidence fields exactly apart from clocks. [Fresh cutoff and measured call detail](DS26-0144-choice.json) · [Second fresh cutoff and call detail](DS29-0491-choice.json) · [Publication seal](prediction-lock.json)
