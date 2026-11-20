# Wide four-center GLRT on two new full-IQ replays

The ±800 kHz four-center detector and public `phase-release` receiver published both calibration arms from both new waveforms under a 512 MiB limit with zero swap. DS26-0014 beat original v5 on both arms. Both positions from DS29-0127 had sub-kilometer errors and fell outside the predeclared relative error criterion. Each calibration arm published 2 of 2 recordings and met both the 5% and 10% criteria on 1 of 2 recordings. [Chart, c = 0](charts/c0/fresh-waveform-wide.png) · [Chart, fitted c](charts/fitted_c/fresh-waveform-wide.png) · [All scores](scores.csv)

| Recording | Error with `c = 0` | Original v5 | Error with fitted `c` | Original v5 |
| --- | ---: | ---: | ---: | ---: |
| DS26-0014 | 0.472 km | 3.415 km | 0.755 km | 3.405 km |
| DS29-0127 | 0.756 km | 0.621 km | 0.721 km | 0.567 km |

All four original v5 options returned the same position on each recording for a given arm. Fitting `c` lowered the DS26 conditional frequency score from 29,922.208 to 29,919.421, while position error rose by 0.283 km. On DS29, fitting `c` raised the score from 26,142.094 to 26,145.264, while position error fell by 0.035 km. Conditional Doppler RMS rose from 97.385 Hz to 97.570 Hz on DS26 and from 75.833 Hz to 75.902 Hz on DS29. [Position and frequency scores](scores.csv)

| Recording | Eligible / read visits | Raw wall | Position wall | Full wall | Full CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0014 | 6,772 / 6,772 | 165.33 s | 50.58 s | 218.24 s | 232.84 s |
| DS29-0127 | 6,403 / 6,772 | 95.01 s | 33.48 s | 129.11 s | 185.77 s |

Each service used CPU 14/15, ran below the 360 s deadline and reached a 512 MiB charged peak with zero swap and zero OOM kills. Both verified all 106 compressed chunks and decoded 10.84 GB of CI16 each. The capture checks excluded 369 DS29 visits for invalid sample support or retune quality. Individual dual-receiver detector calls took at most 20 ms on 1,749 of 6,772 eligible DS26 visits and 4,165 of 6,403 DS29 visits. These are single runs on a shared host and the timings include separate raw and position stages. [Resource receipts](resources.json) · [DS26 service log](DS26-0014-service.log) · [DS29 service log](DS29-0127-service.log)

The two recordings ranked first by the frozen first capture-manifest SHA-256 in their families after excluding the six previous ordinary and wide full-IQ recordings. The inventory after exclusions contained 156 DS26 and five DS29 candidates. Both selected cases passed the installed producer gate, original manifest validation, and truth-free request and causal snapshot checks. The position solver used only newly computed factors. The original v5 references use their capture-era factors. Some prior factor-only studies included these recordings, and both captures come from the same roof. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json) · [Prediction seal](prediction-lock.json) · [DS26 replay native](native/DS26-0014.json.gz) · [DS29 replay native](native/DS29-0127.json.gz)

An XFS directory write stalled the queued DS29 setup before systemd created a service. The original supervisor exited and left an empty directory. The single DS29 scientific service used a local ext4 output directory with the same frozen input IQ and software. [Storage incident](storage-incident.json)
