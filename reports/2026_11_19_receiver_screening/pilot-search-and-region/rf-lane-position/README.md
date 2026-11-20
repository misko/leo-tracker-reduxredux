# Position with one frequency assigned to the original detector

On two five-minute roof recordings, the positions from packets available at recording close had fitted errors of **0.418 km on DS26-0237 and 1.961 km on DS29-0082**. Original no-repair v5 gave 0.271 and 0.517 km on the same recordings. Both exceeded the individual +10% allowance. Even if every assigned packet had been available, fitted errors would have been 0.315 and 2.036 km. [Position distributions and all four original v5 options](charts/README.md) · [Per-recording scores](scores.csv)

| Measurement selection | DS26 visits | DS26 error, zero / fitted (km) | DS29 visits | DS29 error, zero / fitted (km) |
| --- | ---: | ---: | ---: | ---: |
| Original no-repair v5 | | 0.362 / 0.271 | | 0.567 / 0.517 |
| Compact solver on the complete original GLRT | 6,766 | 0.353 / 0.262 | 4,868 | 0.568 / 0.516 |
| Compact solver on the complete fast GLRT | 6,766 | 0.382 / 0.323 | 4,868 | 2.489 / 2.346 |
| Original on one RF, fast on seven, every assigned packet available | 6,766 | 0.388 / 0.315 | 4,868 | 2.044 / 2.036 |
| Same assignment, packets returned by the final scheduled arrival | 6,087 | 0.498 / 0.418 | 4,430 | 1.931 / 1.961 |
| Same clock, omit packets from the original RF | 5,332 | 0.522 / 0.397 | 3,781 | 2.964 / 2.720 |
| Same clock, use packets returned within 20 ms of their visit | 3,104 | 0.600 / 0.502 | 2,112 | 1.562 / 1.390 |

Every row returned both positions. On DS29, adding the original detector's packets to the seven fast frequencies cut fitted error by 0.758 km. On DS26 it raised fitted error by 0.021 km. The 20 ms rule admitted zero packets from the original worker on both recordings. The counts include negative visits. [Measurement hashes and positive probes](support.csv) · [Acquisition clock and queues](../rf-lane-waveform/README.md)

The numerical fit started after the final arrival. It took another **100.7 and 60.2 seconds of wall time** for the by-close inputs, and 36.8 and 32.6 seconds for the 20 ms inputs. Each service had one host core, a 512 MiB limit and zero swap. The complete assignment uses verified detector outputs from saved waveforms. Its timing measures the position fit only. [Position time and memory](position-timing.csv)

The independent ten-recording replay assembled the complete assignment a second way. For both shared recordings the ordered probes, selected frequency, catalogue, region, both positions, frequency scores and scientific counters matched exactly. [Independent comparison receipt](independent-comparison.json) · [Ten-recording comparison](../rf-lane-panel/README.md)

For the by-close inputs, fitting the RF calibration coefficient changed Doppler RMS from 86.79 to 86.69 Hz on DS26 and from 85.06 to 84.82 Hz on DS29. DS26 geographic error fell by 81 m and DS29 rose by 30 m. Each pair used the same observations, causal orbital catalogue, offered region and compact solver. Both recordings came from the same physical roof. A completed recording manifest supplied the repeatable draw of one frequency for this test. A live receiver can provision that frequency when it starts. [Frequency scores and position errors](scores.csv) · [Selection protocol](PROTOCOL.md)
