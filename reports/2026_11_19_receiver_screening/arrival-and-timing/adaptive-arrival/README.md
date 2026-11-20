# Choose four or five pilot timing regions as each visit arrives

The adaptive receiver searches all five regions when no earlier visit is outstanding. If the worker is busy and one waiting slot is free, the admitted visit gets the four stock regions. If both slots are occupied, that arrival drops. The decision uses only the number of unfinished visits. All accepted visits run the same native detector with one context, and both antennas of each visit receive the same search policy. [Admission rule](../../../../tools/pipeline_eval/variants/arrival_policy.py) · [Frozen protocol](PROTOCOL.md)

DS26-0197 and DS29-0316 each have a five-minute saved stream with recorded hardware arrivals. All three policies ran in real time on one fixed host core per recording under a 512 MiB cap with zero swap. Trial order was reversed between recordings for the stock and fifth controls, with the adaptive trial second on both. One run per recording and policy measures what the host actually delivered under its load during that run. The comparison using the same arrival times and scaled paired service costs supplies a separate, deterministic scheduling control. [Frozen host and radio inputs](source-lock.json) · [Controlled queue comparison](../queue-capacity/README.md)

The decoder checks the compressed raw data and the radio sample counters. It prefetches at most eight visits. For every admitted visit, the worker checks both antennas’ emitted native envelope against the original result for the selected timing policy. Position fitting uses the verified emitted visits and the original region and causal orbital catalogue. The reported detector age runs from scheduled delivery through verified emission. The position receiver runs afterward, with its own elapsed and CPU time.

## What arrived during the five minutes

| Recording | Timing regions | Native packets emitted | Valid visits dropped | Packet age P95 | Detector CPU |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0197 | Four | 5,570 | 1,191 | 152 ms | 152 s |
| DS26-0197 | Adaptive | 6,081 | 680 | 118 ms | 190 s |
| DS26-0197 | Five | 6,698 | 63 | 71 ms | 220 s |
| DS29-0316 | Four | 6,717 | 57 | 64 ms | 174 s |
| DS29-0316 | Adaptive | 5,864 | 910 | 151 ms | 185 s |
| DS29-0316 | Five | 3,858 | 2,916 | 305 ms | 151 s |

The adaptive worker used the fifth region on 2,925 DS26 visits and 2,393 DS29 visits. The first run on each core lost the most visits, with 405 DS26 and 105 DS29 inputs late at the decoder. The final runs on those same cores had zero late decoder inputs. Host load changed during the trial, so differences in packet loss include both the admission policy and the conditions under which it ran. The trials accounted for all 13,546 physical visits, including 11 invalid DS26 captures. The detector CPU column sums time on admitted calls and therefore also depends on how many were accepted. [Timing distribution](timing.png) · [Exact counts, percentiles and time boundaries](timing.csv)

## Position from the packets actually emitted

| Recording | Original v5, no repair | Four | Adaptive | Five |
| --- | ---: | ---: | ---: | ---: |
| DS26-0197 | 0.528 / 0.689 km | 0.778 / 0.970 km | 0.796 / 1.058 km | 0.909 / 1.113 km |
| DS29-0316 | 1.007 / 1.011 km | 0.688 / 0.704 km | 0.945 / 0.948 km | 0.197 / 0.202 km |

Each cell gives horizontal error with zero calibration followed by fitted calibration. The three paced policies each returned both fixes, beat original v5 on DS29, and exceeded the 10% error allowance on DS26. An independently measured stock/fifth pair on DS29 had previously produced 0.718 / 0.682 km respectively with fitted calibration on the same physical recording and one waiting slot. The distribution of lost visits changed between trials. [Fitted position distributions](position-charts/fitted_c/adaptive-arrival-position.png) · [Zero-calibration distributions](position-charts/c0/adaptive-arrival-position.png) · [Previous host trials](../../support-preserving/arrival-queue/README.md)

On DS29 the adaptive policy gave the smallest conditional Doppler RMS (118.27 Hz) and the largest fitted position error (0.948 km) of the three policies. The fifth-region policy gave 123.54 Hz and 0.202 km. Each fresh position solve took 48–59 s wall time after the emitted measurements were available. [Exact positions, frequency scores and solver resources](position-scores.csv) · [Four original-v5 controls](position-v5-controls.csv)

## Reproduce the detector chart

The following command reads the sealed per-visit timing and native-output receipts in this folder. Waveform storage and the installed receiver are needed only for another full physical-clock replay.

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.adaptive_arrival_stage
```
