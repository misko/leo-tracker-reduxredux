# What drives the negative-rescue position change?

On both recordings, each subset of differential-only probes increased horizontal error relative to stock when added alone. The combined effect depended on the recording. On DS26-0168, the full union increased error by 667 m at zero c and 677 m at fitted c. The two additions together incurred roughly 520 m more error than the sum of their individual effects. On DS29-0604, the full union incurred 45 m and 63 m of extra error and came closer to stock than either separate intervention. The four new fits and the four measured parent fits each published both calibration arms. [Both-arm scores](scores.csv) · [Factorial contrasts](effects.csv)

| Recording | Stock | Corroborated only | Remainder only | Complete rescue |
| --- | ---: | ---: | ---: | ---: |
| DS26-0168 | 0.805 / 0.796 km | 0.847 / 0.841 km | 0.910 / 0.903 km | 1.472 / 1.473 km |
| DS29-0604 | 0.735 / 0.734 km | 0.921 / 0.950 km | 0.957 / 0.981 km | 0.780 / 0.797 km |

The table lists zero c and fitted c in that order. On each recording, all four cells stayed inside 110% of each of the four original capture-era v5 errors in both arms. The stock endpoint had the lowest error on both recordings under both calibrations. The original v5 references used capture-era detector inputs. [Capture-era v5 references](capture-era-v5.csv) · [Position figures](figures.json)

## Packet and track evidence

The experiment retains every stock packet except for the selected stock-negative probes. It substitutes the complete differential packet for each selected probe. The capture-era output supplies an offline label. The differential winner matched either the capture winner or another gated capture candidate for 118 of 401 additions on DS26-0168 and 132 of 401 on DS29-0604. The remainder contains 283 and 269 additions. Of the 552 total remainder packets, 521 came from capture-negative probes and 31 differed in timing or frequency family from the gated capture candidates. The comparison uses two ADC samples modulo the frame and 1 kHz modulo carrier ambiguity. Capture-era agreement cannot establish whether an individual pilot or satellite assignment was correct. [Agreement ledger](../detector-agreement/probes.csv.gz) · [Reproducible member and packet digests](packets.jsonl.gz) · [Frozen inputs](plan.json)

Every stock observation remained present with exactly the same CFO. Graph grouping did change. In the separate subsets, 89/118 and 107/132 corroborated gains joined tracks, versus 198/283 and 167/269 remainder gains. With the full union, 100 and 116 corroborated gains joined tracks, and 207 and 176 remainder gains joined tracks. On DS29-0604 the full union also left only 57 stock Graph points out of all tracks, compared with 82 for the corroborated subset and 67 for the remainder. On DS26-0168 all three cells except the union offered cavity recovery. These changes establish that the receiver reinterprets existing support as it gains packets. The evidence does not isolate which individual tracks or orbit hypotheses moved either endpoint. [Graph audit](graph-support.csv) · [Measured receiver outputs](positions.jsonl.gz)

## RF fit and measurement boundary

| Recording | Stock | Corroborated only | Remainder only | Complete rescue |
| --- | ---: | ---: | ---: | ---: |
| DS26-0168 | 70.859 / 70.865 Hz | 77.005 / 77.002 Hz | 76.393 / 76.388 Hz | 84.440 / 84.443 Hz |
| DS29-0604 | 95.525 / 95.482 Hz | 95.844 / 95.821 Hz | 98.512 / 98.490 Hz | 96.935 / 96.911 Hz |

Conditional Doppler RMS rose in every cell with additions relative to stock. Conditional scores use the observations admitted by each cell, so the table describes the RF fits on their own support. DS26-0168 had the greater RF RMS increase from the corroborated subset alone and the greater horizontal error increase from the remainder alone. Both directions matter when interpreting the fit. [Conditional RMS and frequency objectives](scores.csv)

The four new runs began at stored native factors and used the same phase-release receiver as the parent experiments, under Linux 512 MiB cgroups with zero swap. Completed external wall times were 126.16 s and 109.78 s on DS26-0168, and 69.00 s and 73.96 s on DS29-0604, in corroborated and remainder order. Peak cgroup usage was 343.6–434.1 MiB. The stock wall times are the position interval of the earlier whole-IQ services on different pins, and stock peak memory covers the whole service. The previous union runs use the same post-detector boundary as the new fits. The two cells are a retrospective diagnosis of saved detector outcomes. [Protocol](PROTOCOL.md) · [CPU, wall, cgroup and swap measurements](resources.csv) · [Closed prediction receipt](prediction-lock.json)
