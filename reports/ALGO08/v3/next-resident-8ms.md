# No larger complete physical recording passed resident admission

None of eight known complete originals above DS30-0107 was resident. The one passive observation found **0 of 804,172 payload pages**, **0 of 1,815 index pages**, and **0 of 17 canonical manifest pages** in cache. All payload and index observations completed without descriptor errors. No raw process launched and no original waveform bytes, manifest bodies or catalogue bodies were read. [Frozen admission](next-resident-8ms-protocol.md) · [Per-file receipt](measurements/next-resident-8ms.json.gz)

Enrollment used the earlier signed inventory and passive-residency receipts, ordered solely by issued visits. A root-owned passive `mincore` query used read-only descriptors at the exact archived segment paths. Since the canonical manifests were cold, the payload and index rows are basename and size diagnostics. The complete compressed sizes matched the prior signed extents for all eight records. A full cache match would still require authentication before launch. Both failed independently here. No solve outcome entered selection.

| Recording | Issued visits | Signed compressed bytes | Payload pages resident / total | Index pages resident / total |
| --- | ---: | ---: | ---: | ---: |
| DS30-0180 | 92 | 111,464,875 | 0 / 27,214 | 0 / 62 |
| DS30-0102 | 124 | 147,843,885 | 0 / 36,096 | 0 / 83 |
| DS30-0084 | 197 | 240,958,254 | 0 / 58,830 | 0 / 133 |
| DS30-0249 | 215 | 259,071,243 | 0 / 63,251 | 0 / 145 |
| DS30-0398 | 303 | 365,047,779 | 0 / 89,126 | 0 / 204 |
| DS30-0306 | 405 | 491,238,921 | 0 / 119,934 | 0 / 272 |
| DS30-0340 | 555 | 686,440,127 | 0 / 167,593 | 0 / 373 |
| DS30-0016 | 808 | 991,734,597 | 0 / 242,128 | 0 / 543 |

The bounded local review found no complete inventory in 12 earlier experiment roots. The retained original DS30-0016 stage has one complete 78,554,951-byte original member and a 22,020,096-byte prefix of the next incomplete member. The packed alternative also covers member zero. The saved receiver experiment on DS30-0169 retains one original member, and the seekable DS30-0008 experiment retains one original member and its split derivative. Other inspected roots contain results, libraries and control metadata. None supplies even the full set of original compressed member lengths for any enrolled larger recording. The previous lossless-read receipts cover their specific member scopes. They cannot supply the absent samples or reconstruct the original full-recording digest. The complete DS30-0107 fixture is the already measured 29-visit case. [Earlier retained-input census](alternate-physical-source.md) · [Measured 29-visit pair](eight-ms-0107-pair.md)

System I/O pressure at observation was 51.73% `some` and 48.60% `full` over ten seconds. The admission ended without warming, staging, reconstruction, original byte reads or new timing. Both calibration and publication comparisons remain unmeasured for this larger physical cohort. Two focused tests passed. [Passive runner](next_resident_8ms.py)
