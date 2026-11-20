# Exclusive physical RF routing

Two full recorded-clock replays assigned one RF per recording to the qualified row-wise original GLRT. The wide four-region worker handled the other RFs. Each worker took both receivers on its assigned visits and had one waiting slot. The original RF was 12,209,687,500 Hz for DS26-0237 and 12,690,312,500 Hz for DS29-0082. [Protocol](PROTOCOL.md)

| Recording | Worker | Assigned | Completed by close | Busy drops | After close | Positive by close | Positive within 20 ms and by close | Worker CPU |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0237 | Wide | 5,920 | 5,332 | 587 | 1 | 2,250 | 1,071 | 93.92 s |
| DS26-0237 | Original | 846 | 755 | 89 | 2 | 216 | 0 | 252.04 s |
| DS29-0082 | Wide | 4,129 | 3,781 | 347 | 1 | 1,367 | 577 | 66.35 s |
| DS29-0082 | Original | 739 | 649 | 89 | 1 | 81 | 0 | 212.20 s |

The 6,766 valid DS26-0237 visits and 4,868 valid DS29-0082 visits each had exactly one assigned detector. Both traces include all physical visits, including 2 and 1,904 hardware-invalid visits, respectively. Every emitted packet matched its independent full-waveform reference exactly. The five after-close packets appear in the full traces and are excluded from cutoff native inputs. [Replay manifest](manifest.json)

Combined detector CPU was 345.96 s on DS26-0237 and 278.55 s on DS29-0082. The earlier concurrent clock replays used 351.70 s and 306.39 s, respectively, with a different CPU allocation and the installed original peak selector. Both current runs used less than 208 MiB peak cgroup memory per detector worker and zero swap. Separate source staging held 10.83 GB and 10.84 GB of authenticated CI16, taking 54.90 s and 55.05 s before replay. Publisher CPU during replay was 1.54 s and 1.39 s, respectively. [Stage figure](rf-lane-stage.pdf) · [Timing data](stage-timing.csv)
