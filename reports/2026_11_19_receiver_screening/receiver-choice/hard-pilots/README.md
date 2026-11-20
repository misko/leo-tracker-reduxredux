# Capture-era pilot winners missed by both timing budgets

Across the six hard recordings, four- and five-center detectors both missed a gate-passing physical counterpart for 1,334 of 25,971 original winning probes (5.14%). Both branches lacked any complete fractional candidate within two samples of the original epoch for 1,264 of those 1,334 probes (94.8%). The two separate control recordings lost 436 of 8,442 original winners in the same comparison (5.16%). The overall deficit rate does not distinguish these hard recordings from those controls. [Per-recording winner census](winner-census.csv) · [Evidence chart](hard-pilots.pdf)

The census verifies the original factor authority, native detector payloads, matching sample clocks and deliveries, original capture exclusions and exact receiver, channel and RF metadata. A physical match uses two wrapped samples and 1 kHz of signed CFO. Alias-only matches use the established 4.4 μs folding period. In the common misses, 670 original winners had negative CFO. There were zero physical matches below the margin threshold across the two sets of published complete fractional candidates. The native factors alone cannot identify which internal search or refinement stages considered a missed candidate.

| Recording | Original winners | Neither branch has a gated physical counterpart | Neither branch has a candidate at the original phase |
|---|---:|---:|---:|
| DS26-0122 | 4,623 | 274 | 252 |
| DS26-0162 | 5,517 | 218 | 212 |
| DS26-0197 | 4,007 | 237 | 229 |
| DS26-0241 | 4,862 | 200 | 190 |
| DS29-0082 | 1,868 | 176 | 168 |
| DS29-0357 | 5,094 | 229 | 213 |

## Representative halves on real IQ

The intervention runs the same differential FFTW scorer independently on each half of the recorded 20 ms visit, zeroing the other half while preserving the original sample grid. The stronger normalized peak becomes one additional region beside the original four. The compiled fifth-center ABI retains the original top-eight, all supported CFOs, exact GLRT and fractional confirmation. The archived original winner enters evaluation after the detector returns. [Protocol](PROTOCOL.md) · [Prospective source and sample lock](source-lock.json)

The nine hash-selected hard visits came from five recordings. DS26-0122 had no eligible common miss in the frozen early-segment bound. DS26-0197 had one eligible distinct visit. Each control recording supplied one matched visit. Fresh stock and released-fifth projected rows were byte equal to their respective archives on both receivers in all 11 visits. [Full waveform witness](waveform.json.gz)

| Detector | Selected physical targets recovered | Held physical winners retained | Gated records across both receivers | Host CPU p50 | Host wall p50 | Wall ≤20 ms |
|---|---:|---:|---:|---:|---:|---:|
| Four centers | 0/9 | 2/2 | 56 | 16.77 ms | 18.18 ms | 20/33 |
| Released fifth center | 0/9 | 2/2 | 60 | 20.82 ms | 21.85 ms | 11/33 |
| Representative-half fifth | 1/9 | 2/2 | 62 | 24.05 ms | 24.66 ms | 2/33 |

All nine selected original integer epochs fell outside the genuine four- and five-center coarse timing regions. The representative-half variant put one inside its extra region. On DS29-0357 visit 3 receiver 1, the second half nominated epoch 10,237 and the unchanged GLRT made +508.24 kHz the winning physical pilot. Its CFO was 33.8 Hz from the original and its fractional epoch within 0.001 sample. The other eight targets remained outside the evaluated regions. The branch changed 15 of 22 requested lane hints and added two gated records with zero alias-aware losses relative to the released fifth on the measured rows. [Qualification data](qualification.json)

Zero and Gaussian controls produced zero gated candidates. All arms kept the eight weak and strong signed lane targets. Both fifth-center methods recovered all four one-frame lane targets, while four centers recovered zero. Host timings use CPU 6 at nice 15 with one numerical thread. Under shared load, half-bank wall p95 was 244 ms and CPU p95 was 32.16 ms. The waveform witness measures candidate recovery. Geographic error and track geometry remain unmeasured for this variant. [Per-call native timings](timing.csv)

## Reproduce the chart and counts

```sh
python -m tools.pipeline_eval.qualification.hard_pilots_results --out /path/to/local/output
```

The chart reads sealed receipts in the checkout. Real-IQ reproduction uses `tools.pipeline_eval.qualification.hard_pilots_eval replay` with the bound center-union, stock and FFTW libraries. [Evidence seal](evidence-lock.json)
