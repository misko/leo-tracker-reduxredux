# How much field accuracy can choosing a calibration recover?

The first 11 paired originals yielded nine common fixes. Seven had larger fitted error with the candidate. On all seven, **even a selector given the true position** would still have higher error than ALGO08v3 if it could return any point on the shortest arc between the candidate's two published positions. For example, on DS30-0452 the candidate's fitted error was 1,907 m. Its best possible interpolated error was 1,884 m, versus 331 m for ALGO08v3. This prices one specific change to the output. Refitting the raw measurements or changing which observations enter the fit can produce positions outside this arc. [Frozen protocol](calibration-blend-bound-protocol.md) · [Spherical distance calculation and report generator](full_successor_score.py)

| DS30 recording | ALGO08v3 error, zero / fitted (m) | Candidate error, zero / fitted (m) | Best on candidate arc (m) | ALGO08v3 RF RMS, zero / fitted (Hz) | Candidate RF RMS, zero / fitted (Hz) |
|---|---:|---:|---:|---:|---:|
| 0019 | 744 / 842 | 435 / 375 | 375 | 143.7 / 143.7 | 174.6 / 174.7 |
| 0049 | 1,826 / 1,420 | 4,472 / 4,040 | 4,040 | 129.7 / 129.7 | 168.6 / 168.8 |
| 0086 | 402 / 410 | 371 / 382 | 371 | 130.4 / 130.1 | 179.8 / 180.1 |
| 0107 | Withheld | Withheld | — | — | — |
| 0124 | 1,143 / 1,145 | 2,022 / 2,006 | 2,006 | 103.3 / 103.4 | 136.4 / 136.4 |
| 0178 | 466 / 387 | 705 / 605 | 605 | 124.4 / 124.3 | 159.8 / 159.7 |
| 0220 | 318 / 369 | 1,412 / 1,371 | 1,371 | 138.1 / 137.8 | 159.8 / 159.7 |
| 0274 | 172 / 206 | 889 / 934 | 889 | 99.8 / 99.7 | 130.3 / 130.2 |
| 0330 | 1,037 / 916 | 1,089 / 1,017 | 1,017 | 88.8 / 88.7 | 125.6 / 125.6 |
| 0397 | Solver failure | 736 / 878 | 736 | — | 139.9 / 139.7 |
| 0452 | 378 / 331 | 1,884 / 1,907 | 1,884 | 104.7 / 104.5 | 133.6 / 133.5 |

Ten recordings had already been scored when this diagnostic was designed. Six of their eight common fixes regressed and all six remained worse after the ideal selection. DS30-0220 was the first additional case named before inspection. Both builds fixed and its irreducible gap under this choice was 1,002 m. The second and third assigned checks are DS30-0144 and DS30-0170. The initial sealed combined export was `bceb23d2c1cb3fe0a4e26c4e377ef69fdd8899fd57b990a32c983491c1facf5b`. Each endpoint and RF RMS came from a verified original-file pair. Region, observation packet and search budget are shared across the two calibrations within each build. Different builds use different receiver packets. All 11 attempts keep their measured runtime, including the withheld and failed attempts. [Field comparison design](full-successor-field-protocol.md)
