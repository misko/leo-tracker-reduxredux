# Complete catalogue parsing on two real snapshots

Changing the checksum in the public parser reduced complete parse CPU by a median of 61% on each causal catalogue. The timer starts with the text already in memory and stops when the parser returns every validated satellite. Each of six paired repetitions alternated which checksum ran first on the same host CPU. [Timing observations](stage.csv) · [Paired timing figure](stage.pdf)

| Snapshot | Satellites | Scalar → public CPU, ms | Scalar → public elapsed, ms | Median paired CPU saving |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 11,142 | 101.85 → 39.63 | 105.66 → 44.12 | 61.16% |
| DS29-0082 | 11,185 | 99.02 → 38.56 | 100.17 → 38.98 | 61.08% |

After each parse the benchmark compared all satellite names, catalogue IDs, SGP4 return codes, positions and velocities at the recording cutoff and 30 seconds on either side. All 66,981 satellite-time states across the two catalogues matched byte for byte on every pair. Disk reads, propagation and position fitting run outside the parser timer. The receiver experiment measures the smaller effect on complete processing. [Source and state hashes](evidence.json) · [Benchmark source](../../../../../tools/pipeline_eval/qualification/catalog_parser.py) · [Complete receiver comparison](../README.md)
