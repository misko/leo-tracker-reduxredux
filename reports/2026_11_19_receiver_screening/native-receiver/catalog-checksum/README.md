# Frozen ASCII TLE checksum in the compact receiver

The public catalogue parser was also timed through validation and construction of every satellite in two snapshots. Median paired CPU fell by 61% on each. [Complete parser benchmark](repo-parser/README.md)

The production checksum reduced preparation CPU by 1.15–2.89 seconds on three hash-selected recordings and preserved every compact v5 position, frequency score, track digest, and terminal decision. Complete-service CPU and wall moved in both directions. The paired full-service timings leave the overall latency effect unresolved.

## Measured work

Each branch ran on the same pinned CPU for a given recording with 512 MiB of cgroup memory, zero swap, and a 180-second limit. All six services completed. The installed phase release supplied the GLRT observation preparation, polynomial fits, causal TLE and SGP4 work, and both compact v5 searches. The candidate compiled only `element_line_checksum` and `_CHECKSUM_WEIGHTS` from production source `b6a62ebf9832fc9684fd5a8dc19767ebed311a01688903b2c2a6cfcd5dde80d4`. Both branches counted checksum calls with the same wrapper.

The pairs used 8,024, 7,290, and 5,843 compact orbit projections on DS26-0162, DS29-0519, and DS26-0197, respectively. Each pair agreed on its complete numerical result, including the trajectory selection, checksum counts, and final coordinate and score for each calibration arm. All observed prefixes qualified for the ASCII path.

| Recording | Checksum calls per service | Preparation CPU, s | Service CPU, s | Service wall, s | Peak memory, MiB |
|---|---:|---:|---:|---:|---:|
| DS26-0162 | 1,147,388 | 18.32 → 15.47 | 99.36 → 111.33 | 109.78 → 115.16 | 438.18 → 434.89 |
| DS29-0519 | 449,754 | 11.33 → 10.18 | 70.63 → 62.23 | 70.98 → 62.31 | 355.79 → 402.32 |
| DS26-0197, shifted | 1,069,388 | 18.42 → 15.52 | 66.46 → 68.37 | 104.45 → 93.79 | 327.51 → 370.15 |

The causal catalogue and phase work saved 1.16–3.12 CPU seconds. Track preparation varied by at most 0.20 seconds and made zero checksum calls. A five-repetition checksum test on one actual snapshot per recording measured median CPU costs of 3.59–3.68 µs per line for the installed function and 0.29–0.34 µs for the frozen function. Individual repetition ranges were 3.56–3.87 µs and 0.29–0.35 µs. Multiplying the paired per-call difference by actual service counts gives roughly 1.5–3.8 CPU seconds of checksum work per service. The compact search accounted for most of the elapsed time. Concurrent host work and the one service per branch per recording limit what the end-to-end timing can resolve. [Numerical chart](stage.png) · [Stage data](stage.csv) · [Service receipts](resources.json) · [Parity](parity.json)

## Geographic and RF results

All six primary services published both calibration arms. The surveyed location for DS26-0197 was 2.704 km inside the shifted tile. Its c = 0 and fitted c endpoints were 2.587 km and 2.411 km inside, respectively, so both passed the 20 m publication guard. The fitted c arm increased geographic error in all three recordings. Its RF RMS and frequency objective improved slightly on DS26-0162 and increased on the other two recordings. The table reports each calibration pair shared by the installed and frozen checksum branches.

| Recording | Geographic error c = 0 → fitted c, km | RF RMS c = 0 → fitted c, Hz | Frequency objective c = 0 → fitted c |
|---|---:|---:|---:|
| DS26-0162 | 0.402 → 0.417 | 47.467 → 47.460 | 37,386.16 → 37,369.65 |
| DS29-0519 | 0.235 → 0.306 | 76.458 → 76.524 | 33,820.24 → 33,821.52 |
| DS26-0197, shifted | 0.514 → 0.677 | 68.784 → 68.787 | 29,828.41 → 29,833.61 |

Original-offer charts include the four frozen v5 reference roles. The shifted charts show the matched branches on the shifted input. The results were sealed before reference geography was scored. [c = 0 original](charts/c0/catalog-checksum-original.png) · [Fitted c original](charts/fitted_c/catalog-checksum-original.png) · [c = 0 shifted](charts/c0/catalog-checksum-shifted.png) · [Fitted c shifted](charts/fitted_c/catalog-checksum-shifted.png) · [Geographic scores](geography.csv) · [Frequency scores](frequency.csv) · [Prediction seal](prediction-lock.json)

## Fixed withholding control

DS26-0102 reused the earlier study's fixed near-omission offer after the primary shifted offer published. Both checksum branches reached the tile face in both calibration arms and withheld publication while retaining identical forced coordinates. Each service made 939,498 checksum calls. Installed and frozen preparation took 17.08 and 13.75 CPU seconds. The complete services took 72.58 and 72.69 wall seconds on CPU 17. This separate control verifies the guard behavior on a previously studied input. [Control outcomes](guard-control/result.json) · [Control seal](guard-control/prediction-lock.json)

## Validation behavior

`ELEMENT_LINE_LENGTH`, `_CHECKSUM_COLUMN`, and `_validate_element_line` matched between the release and production source at the syntax-tree level. The line validator retains width, prefix, recorded-digit, and checksum checks in the same order. The checksum-only comparison agreed on 136 line inputs and 17 catalogue inputs. The synthetic corpus covered all ASCII byte values, the 68-column slice, Unicode decimal digits, Unicode digit conversion errors, observable `str` slicing, valid names and Alpha-5 IDs, and malformed records after valid records.

All 139 sealed causal snapshots parsed in both versions. Their 1,551,154 ordered element sets agreed in catalogue IDs, names, and hashes of 21 parsed SGP4 fields. The installed parser separately prevalidates catalogue IDs through `from_alpha5`. The production public parser uses SGP4 directly, so both checksum-valid lines with the synthetic identifier `A@001` pass production parsing and are rejected by the installed parser. Isolating the checksum in the installed parser preserves that rejection. [Catalogue and checksum audit](catalogue-audit.json) · [Registration](PROTOCOL.md) · [Source seal](source-lock.json)
