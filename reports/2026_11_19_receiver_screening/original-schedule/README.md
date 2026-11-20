# Keeping the original pilot search from saved I/Q to position

On DS29-0519, the 256-point coarse FFT reproduced all **62,048** original ordered candidates over **6,771** scheduled stereo visits. The compact solver returned the same **235 m** error with zero RF calibration and **306 m** with fitted calibration as the 512-point replay. The four original v5 settings gave **248 m** and **319 m**. Both replays searched the original pilot anchors on both antennas, including the wider search whenever only one antenna passed. [Complete replay and matched v5 distributions](fft-waveform/README.md)

| Five-minute DS29-0519 replay on eight Intel host cores | Earlier 512-point run | Stored 256-point run |
| --- | ---: | ---: |
| Elapsed through raw processing | 577.33 s | 394.96 s |
| Elapsed from raw launch through the position | 633.39 s | 446.26 s |
| Total detector CPU across valid visits | 3,134.02 s | 2,525.91 s |
| Coarse search CPU | 1,570.77 s | 1,121.81 s |
| Visits reaching the detector output within 20 ms | 0 / 6,727 | 0 / 6,727 |

The complete runs used the same chunks and core assignments at different times. In the separate interleaved comparison of 40 pairs, shortening the FFT saved **4.18%** of complete-detector CPU. The full 256-point replay still spent **1,404 CPU seconds outside coarse search** on 300 seconds of radio. These are host measurements. The portable binaries have numerical checks under ARM emulation. Physical embedded throughput and independent-site wideband position accuracy are open. [Per-visit clocks](fft-waveform/paired-timing.csv) · [Counterbalanced timing](../coarse-and-navigation/fft-length/README.md) · [Portable runtime](portable-coarse/README.md)

The new public `--accelerated` command was also tested on DS26-0020, selected by its signed window count before geographic scoring. The original mixed-core run reached its 600 s raw limit with 105 of 106 closed chunks, so it returned no position. A completion check on eight performance cores reproduced every field and rank of all **62,161** archived candidates over **6,764** scheduled visits. Raw elapsed was **282.43 s** for **299.97 s** of recorded deliveries. The full command returned in **345.23 s**, with the same two coordinates as an independent fit on the original factors. Median detector wall time per valid visit was **260.60 ms** and **0 of 6,761** valid visits reached the 20 ms deadline. The completion run used **2,002.39 detector CPU seconds**. This is an offline batch-throughput result on eight Intel desktop cores. [Primary timeout, completion and paired position evidence](accelerated-command/README.md)

## Full-recording checks against v5

Each row follows a particular change through all recorded samples and a fresh position decision. Errors are horizontal distances in metres. Raw time covers detector processing on eight host workers. The original v5 range spans its no-repair, selective-gap and two omitted-track settings. DS26 and DS29 were recorded at the same roof.

| Recording and change | Compact error, zero / fitted calibration | Four v5 errors as ranges, zero / fitted | Raw elapsed |
| --- | ---: | ---: | ---: |
| DS26-0020, accelerated public command on eight performance cores | 813 / 734 m | 756–818 / 670–739 m, three returned | 282 s. [Position, primary timeout and completion](accelerated-command/README.md) |
| DS26-0237, row-wise peak selection | 353 / 262 m | 362 / 271 m | 459 s. [Position and time](../receiver-deadline/selector-waveform/README.md) |
| DS29-0082, pruned fine-frequency search | 568 / 516 m | 115–567 / 486–517 m | 497 s. [Position and time](../pilot-search-and-region/field-exact-waveform/README.md) |
| DS29-0519, shorter coarse FFT | 235 / 306 m | 248 / 319 m | 395 s. [Position and time](fft-waveform/README.md) |

DS26-0020 falls outside the original common 127 DS26 recordings. Original v5 with two omitted tracks timed out on it. The accelerated completion was within 10% of each of the three v5 settings that returned a position, in both calibration arms. Its first attempt returned no position. [Complete DS26 selection and recorded outcomes](../redesign/roof-selection/native/README.md)

Fitting the RF-dependent calibration moved DS26-0020's error from 813 to 734 m. Its conditional RF RMS moved from 72.547 to 72.512 Hz and its frequency objective from 29,906.68 to 29,915.61. On DS29-0519, the same calibration choice moved geographic error from 235 to 306 m, RF RMS from 76.458 to 76.524 Hz and frequency objective from 33,820.24 to 33,821.52. Each comparison holds the returned pilot stream and solver settings fixed. [DS26 geography and frequency scores](accelerated-command/scores.csv) · [DS29 geography and frequency scores](fft-waveform/scores.csv)

Across the separate 20-recording audit, the compact solver with original pilot measurements met the individual 10% error allowance against no-repair v5 on **19/20** recordings in both calibration arms. One fit timed out. The fast four-region detector returned all 20 fixes and met the allowance on **12/20** in each arm. Counting a success only when it meets the allowance against **all four** original v5 settings on that recording gives **18/20** and **12/20**, respectively, in each arm. Those trials used archived complete detector factors and the same roof. [Per-recording distributions](../retry-and-transfer/cascade-audit/charts/index.html) · [Individual errors and all four references](../retry-and-transfer/cascade-audit/scores.csv)

On the broader 135-recording panel, the compact secant solver returned every fix and met the 10% allowance against no-repair v5 on 131 recordings in each arm. Requiring it to meet the allowance against every v5 option gives **121/135 at zero calibration and 122/135 with fitted calibration**. That stricter comparison chooses the most accurate original option separately for each recording after seeing the survey. [Broader panel scores and selection](../secant-full/README.md) · [All errors by recording](../secant-full/per-recording.csv)

## What changed and what reached a position

| Change | Measured result |
| --- | --- |
| Run the standalone C detector from raw dual-antenna samples | On six held visits across three capture producers, it generated all 112 ordered seeds, reproduced both gate-driven retries and matched every discrete gate. Two equivalent duplicates exchanged internal identities. Complete x86 medians were 214 ms with the initial search and 355 ms with a retry. [Native and ARM numerical checks](portable-coarse/README.md) |
| Run the C verifier inside the original acquisition loop | All 224 candidates, four real peer retries and downstream candidate ranks matched within the declared tolerances on 12 held visits. Depending on recording, complete resident CPU fell 11–42% with the prepared coarse detector. [Per-recording timings](verifier-integration/README.md) |
| Estimate alternate coarse frequency rows | Interpolation saved 33.28 ms per held visit at the median and reproduced the full output on two of six visits. Rechecking the shortlist restored six of six and cost 13.76 ms more than evaluating the complete 256-point bank. [Candidate and timing distributions](coarse-cfo/README.md) |
| Reuse work when a fine search repeats | All 380 timed calls returned the same outputs. Caching a repeated verification saved 21.2% mean CPU on eight such visits. Across 20 visits selected without regard to the result it saved 1.1% on average. [Timing and frequency of rechecks](fine-epoch-reuse/README.md) |
| Batch the spectral verification arithmetic | All 384 ranked outputs matched on 20 stereo visits. The spectral step fell from 5.10 to 3.98 ms. The complete detector took 4.95 ms more CPU at the paired median. [Full-detector measurements](spectral-rewrite/README.md) |
| Share polynomial support calculations and shorten TLE checksum validation | On three complete primary pairs, preparation CPU fell from 13.61, 17.84 and 18.70 seconds to 11.12, 13.26 and 14.11 seconds. The selected tracks and both positions matched on all three. On a shifted fourth offer the original service timed out. A separate completion check reproduced both withheld decisions. [Whole services and geographic outcomes](track-preparation/README.md) |
| Correct the fast detector's signed tracking frequency | An offset learned on eight recordings changed the median absolute frequency difference from 17.350 to 17.295 Hz on 22,163 shared winners in six other recordings. Both the corrected and original fast stream met the individual 10% position allowance on three of six recordings in each calibration arm. [Position distributions, reversed-sign control and clocks](fast-calibration/README.md) |
| Reserve original-detector visits for predicted geographic information | Six held recordings supplied 2,353 original stereo calls per method. The geometry selector increased its predicted information gain, but subsequent measurements favored the nominal region less than a matched hash did on all six. Geometry met the v5 10% allowance on three of six with one timeout. The original detector met it on six of six. [Forecast controls and position results](geometry-schedule/README.md) |
| Infer range change from fractional pilot timing and carrier Doppler | On four roof recordings the physical pilot-timing model lost to clock-only and reversed-sign controls. The joint receiver withheld all 12 offers. A separate blinded simulated site reproduced the timing sign and also withheld all three offers. [Range residuals, forced errors and decisions](code-carrier/README.md) |
| Transfer beacon frequencies between independent physical sites | Eight sites supplied 81 measured arcs and 79 distinct satellite identities. Each site had at most one usable donor frequency even with later measurements and known identities. A receiver clock offset absorbs that single difference. Every transfer offer was withheld. [Donor observations and containing and missing-region distributions](beacon-transfer/README.md) |
| Estimate position from independently measured Prague Doppler tracks | Two dates supplied 11 captures, 19 tracks and 7,161 Doppler points at one additional roof. The held frequency curves agreed with the supplied satellite paths more closely than with shuffled samples. The receiver withheld on every containing, near-missing and far-missing offer. The source tracked frequencies using survey-assisted satellite windows and supplied processed orbit states. This tests position information given those tracks and orbits. A blind acquisition test at that site would require independent inputs. [Prague measurements and decisions](prague-transfer/README.md) · [Czech Technical University source](https://hdl.handle.net/10467/184304) |

The benchmark plots give every tested recording weight, including withheld positions and timeouts. Each rooftop position chart uses the four v5 settings on the same recordings. The zero and fitted RF calibration runs share the observations, candidate sets and search budget wherever calibration is identifiable. Experiments ending at a detector or preparation stage show the measured quantities at that stage. [Browse each modification](benchmark/index.html) · [Download charts and CSVs](benchmark/modification-charts.zip)

## Reproduce the figures or run the receiver

Regenerate the per-change distributions and stage figures in a new directory from the sealed evidence.

```sh
.venv/bin/python -m tools.pipeline_eval benchmark \
  --study reports/2026_11_19_receiver_screening/original-schedule \
  --pack --out /var/tmp/leo-original-schedule-benchmark
```

The public acquisition command runs the stored 256-point FFT, row-wise peak selector and four-frame fine-frequency search together. It authenticates the saved waveform, runs the original gate-driven schedule and feeds the newly measured pilots to the compact solver. Supply cores available to the local process and a fresh output directory. [Command reference](../../../tools/pipeline_eval/README.md) · [Case selection and run limits](accelerated-command/PROTOCOL.md)

```sh
.venv/bin/python -m tools.pipeline_eval.original_receiver \
  --accelerated --case DS26-0020 --out /var/tmp/original-ds26-0020 \
  --cpus 0 1 6 7 10 11 17 18 --raw-limit 600 --position-limit 180
```
