# Causal reception changes explain gains beyond static calibration

A frequency-free predictor of changing receiver outcomes beats frozen early calibration on all six development recordings and the signed geometry model on four of six. Its mean later gain over the simpler P model is positive, but only three of six recordings improve. It therefore fails the predeclared four-of-six criterion for replacing P. Retain it as an additional response control, not a demonstrated sub-kilometre method.

| Causal predictor compared with | Mean later gain, nats/window | Positive recordings |
|---|---:|---:|
| Training background | +0.401942 | 6/6 |
| Frozen early local calibration | +0.416736 | 6/6 |
| P receiver/rate/time model | +0.079086 | 3/6 |
| U unsigned geometry | +0.118059 | 4/6 |
| O signed geometry | +0.121691 | 4/6 |

| Recording suffix | Later windows | Gain over P | Gain over O |
|---|---:|---:|---:|
| 39ac2b14d1bb5f0f | 117 | −0.018314 | −0.035938 |
| 3ebf3526172258af | 235 | −0.113290 | −0.048154 |
| 4c56320fb5ca6994 | 218 | +0.229057 | +0.231570 |
| 851486cc2a1acd99 | 331 | +0.175934 | +0.175896 |
| 9d7b6a0db558703a | 243 | +0.317896 | +0.338839 |
| c559f436d578c9bd | 219 | −0.116768 | +0.067932 |

## Method and evidence

The predictor maintains exponentially decaying counts of neither receiver, RX0 only, RX1 only and both. It combines them with 20 fixed pseudo-observations from the other-five-record background. At each actual timestamp it decays previous counts, predicts the normalized four-category distribution, scores the observation and only then adds that observation. Reception history continues into later windows. This is not a satellite detector, a physical gain estimate or a direction model.

All six folds select a 10-second decay time from the predeclared 1/10/30/100-second grid using the other five recordings' reception scores only, with equal recording weights. No omitted-record category or later category chooses the time. These data remain reused development evidence. The `held_frequency` role is scored as receiver categories here, not frequency residuals.

The [protocol](PROTOCOL.md) predates execution. [run.py](run.py) verifies exact original training-window membership and later denominators. [results.json](results.json) stores every training grid, selected time, source hash and per-window predictive distribution. Four tests pass: current/future categories cannot alter the current prediction, probabilities normalize and begin at the background, long gaps forget history, and reversed timestamps fail. Execution completes in under one second under the 60-second cap.

This result adds a concrete comparison required before attributing reception gains to geometry. A future direction model must improve over causal occupancy prediction as well as the existing P baseline, retain candidate-permutation and receiver-swap controls, and subsequently improve an independent frequency endpoint. The result does not justify multiplying receiver-state likelihoods into a candidate-set likelihood that already scores detection counts; that would count evidence twice.

Sources: [original paired-state model](../2026_09_28_rx_paired_state_cv/README.md), [frozen local calibration](../2026_09_30_rx_local_response/README.md), [association bridge requirements](../2026_09_28_rx_paired_state_cv/NEXT-GATE.md).

No RF collection, IQ processing, geographic fit, production change or remote publication occurred.
