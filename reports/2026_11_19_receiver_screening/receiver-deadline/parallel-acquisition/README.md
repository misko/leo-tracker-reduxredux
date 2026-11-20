# Concurrent detector acquisition at recorded pace

Each 300-second recording ran the wide four-region detector and prepared original detector on separate host cores with one waiting visit per worker. Both detectors received the same physical arrivals. The final recorded arrival set the cutoff, including hardware-invalid arrivals. Each measured dual-antenna packet matched its independent full-waveform reference exactly. [Protocol](PROTOCOL.md) · [Measurement manifest](manifest.json)

| Recording | Detector | Valid visits | Completed by close | Busy drops | Later drain | Positive within 20 ms by close |
|---|---|---:|---:|---:|---:|---:|
| DS29-0082 | Wide four-region | 4,868 | 4,088 | 779 | 1 | 585 |
| DS29-0082 | Prepared original | 4,868 | 592 | 4,274 | 2 | 0 |
| DS26-0237 | Wide four-region | 6,766 | 6,275 | 490 | 1 | 1,058 |
| DS26-0237 | Prepared original | 6,766 | 593 | 6,171 | 2 | 0 |

Every valid visit contributes to the plotted denominator. A positive packet contains at least one candidate that passed the fractional margin gate. The 20 ms age starts at the recorded arrival. [Chart PNG](parallel-recorded-acquisition.png) · [Chart PDF](parallel-recorded-acquisition.pdf) · [Underlying CSV](stage-timing.csv)

Source preparation read 8.40 GB and 8.15 GB of compressed capture data for DS29-0082 and DS26-0237. Decoding and verified readback took 32.89 and 33.81 seconds and staged 10.84 and 10.83 GB of CI16 IQ in separate cgroups. Every stage and detector cgroup recorded zero swap. The figures describe one paired replay per recording. [Source stage receipts](stage.json)

The acquisition and staging `.py.gz` files preserve the as-run source. Their decoded SHA-256 values are in `manifest.json`.
