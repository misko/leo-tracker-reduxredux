# Avoid reconstructing nonregional orbits in the compact receiver

The installed phase-release receiver first constructs the full causal catalogue to screen satellites against the offered region. The previous-orbit, genuine-previous and phase-history passes later read many of those same snapshots. These passes use only already-selected regional objects. The overlay constructs just those objects after the full snapshot text has already passed validation in the same scan. The layout includes no new source files or shared objects in the installed receiver.

The scan retains a bounded set of at most 512 SHA-256 digests for fully constructed snapshot texts whose textual IDs agreed with the SGP4 IDs. A cold, changed or mismatched snapshot always runs the original full parser. Each stage still reads and authenticates the original causal snapshots and keeps its original epoch and provenance ordering. Each retained orbit gets a fresh SGP4 object. The original text cache and its last-use release remain in place. Earlier work reduced repeated checksum evaluation and evicted cached text at the end of history. This experiment removes repeated orbit-object construction downstream of the regional screen.

The fresh comparison uses two complete ordinary native inputs and two existing capture-era inputs. Each A/B pair ran on the same pinned core, with the original offer, exact GLRT and TLE bytes, all numerical search budgets, both calibration arms and a physical 512 MiB zero-swap cap. The control and candidate emit the same preparation checksums and work counters. Two earlier passes stopped in the shared diagnostic formatter before final fitting. The first encountered a NumPy scalar and the second an array. Both sets of original process logs and plans remain in `preflight/`. The timed run uses `tolist()` for both representations and keeps the predeclared numerical settings.

## Measurements

All eight workers completed. In each pair, the prepared catalogue, selected and previous elements, historical phase inputs and computed forecast had the same digest. After excluding stage timings, the serialized results matched exactly, including both calibration arms' coordinates, conditional RF RMS, frequency scores, projection and initial-search counts, and final decision. [Pairwise parity](parity.json) · [Both calibration charts](charts/index.html)

| Recording | SGP4 constructions, stock → regional | Native preparation wall (s) | Complete CPU (s) | Complete wall (s) | Peak cgroup charge (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 ordinary | 1,025,162 → 438,408 | 21.41 → 12.17 | 69.56 → 58.03 | 86.73 → 61.02 | 267.7 → 264.4 |
| DS29-0082 ordinary | 1,263,843 → 598,536 | 16.74 → 12.37 | 38.75 → 34.82 | 39.93 → 35.20 | 263.8 → 263.0 |
| DS26-0112 capture-era | 1,448,238 → 587,727 | 18.23 → 14.19 | 81.44 → 85.23 | 83.41 → 85.66 | 325.8 → 332.7 |
| DS29-0127 capture-era | 1,252,606 → 547,503 | 18.34 → 14.36 | 48.84 → 50.09 | 50.89 → 58.59 | 265.3 → 259.5 |

The candidate skipped 2,817,675 of 4,989,849 SGP4 constructions (56.5%) and cut native-preparation wall time in all four pairs. Across the series, summed preparation wall fell 28.9%, total CPU 4.4% and complete elapsed time 7.9%. Complete timing improved in two pairs, while later search time grew in both capture-era pairs despite identical recorded numerical work. Ordinary pairs ran stock first and capture-era pairs ran candidate first, so elapsed-time interpretation is tied to the individual matched runs. The largest measured process RSS was 367.1 MiB in stock and 374.3 MiB in the candidate. [Work and CPU figure](compact-cost.pdf) · [Measured resource records](resources.csv)

Both installations have 78 source files and the same two compiled kernels. The candidate edits four of the released files and adds 46 net lines, including the common measurement witness. The instrumented control edits two files and adds 35 net lines. [Installed diff](installed-delta.patch) · [Source counts](complexity.json)

## Reproduce

Install the optional overlay in a new local directory, then use the same argument interface as the existing installed phase-release worker.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.compact_catalogue_build /tmp/region-catalogue
.venv/bin/python -IB /tmp/region-catalogue --help
```

The [protocol](PROTOCOL.md) and [source lock](source-lock.json) identify the four measured recordings. [Resource and work counters](resources.csv), [both-arm scores](scores.csv), [complete preparation and result parity](parity.json) and the [standard position charts](charts/index.html) are reproduced offline from the sealed prediction rows:

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.compact_catalogue_results
```
