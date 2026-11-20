# Batched fine-CFO replay on the complete screened DS29-0519 recording

The fresh replay authenticated **6,771 scheduled visits** and reproduced all **62,048 ordered published candidates** exactly. All eight raw workers completed on their first attempt in **577.33 seconds**. Every valid visit exceeded the 20 ms detector wall budget. [Native audit](audit.json) · [Timing and endpoint comparison](comparison.json)

The waveform came from the installed screened lower-edge capture release. The original request binds the 25 km offer and 43 causal TLE snapshots. The eight complete replay services run fixed prepared full grids, the row-wise peak selector, the batched binary64 fine-CFO transform, and the original physical refiners. [Source lock](source-lock.json) · [Protocol](PROTOCOL.md)

## Native fields

All 106 compressed chunks authenticated, including 6,727 valid visits and 44 original exclusions. The first-visit checks included the four previously qualified visits, three other sequence-hash visits and one archived exclusion. The installed, scalar-pruned and batched implementations agreed on complete public responses, projected factors and acquisition attempts in all eight checks. [Launch receipt](receipts/smoke.json)

The complete batched stream matched all **13,454 original physical probes**, including 22 empty probes and 14,464 gate passes across 4,637 probes. Every persisted candidate field, rank mask, empty row, gate, delivery-clock record, UTC anchor and exclusion matched the original archive. The canonical probe digest is `sha256:e899f7e45f9e29f626e6a8d59d8d25ad593bfa8588a300c77ad6a85bda04885c`. The detector ran 15,210 full folded grids and 121,680 fine-CFO calls without a fine fallback. [Fresh native stream](native.json.gz) · [Fine-call ledger](fine.csv) · [Coarse grid ledger](coarse.csv)

## Position and RF calibration

Independent compact services on fresh and archived factors returned identical unrounded endpoints in both calibration arms. Each fit kept its observations, candidates, priors and search budget matched across the arms. Predictions were sealed before geographic scoring against the held survey. The earlier complete fast controls used the same capture, causal request, catalogue and offer. [Prediction lock](prediction-lock.json) · [Geographic scores](scores.csv) · [Capture-era v5 controls](v5-roles.csv) · [Position chart, c = 0](charts/c0/modifications.pdf) · [Position chart, fitted c](charts/fitted_c/modifications.pdf)

| Position input | Error at `c = 0` (km) | Error with fitted `c` (km) | Conditional RF RMS, zero / fitted (Hz) |
|---|---:|---:|---:|
| Fresh batched original waveform replay | 0.23499 | 0.30588 | 76.4584 / 76.5237 |
| Archived original factors, independent compact fit | 0.23499 | 0.30588 | 76.4584 / 76.5237 |
| Earlier complete fast four-region replay | 0.33430 | 0.32371 | 90.2303 / 90.3410 |
| Earlier complete fast five-region replay | 0.66460 | 0.76268 | 89.0001 / 89.0351 |
| Capture-era v5 no-repair | 0.24831 | 0.31923 | 100.7451 / 81.3416 |
| Capture-era v5 selective gap | 0.24831 | 0.31923 | 100.7451 / 81.3416 |
| Capture-era v5 omitted-track-one | 0.24831 | 0.31923 | 100.7451 / 81.3416 |
| Capture-era v5 omitted tracks | 0.24831 | 0.31923 | 100.7451 / 81.3416 |

Fitted `c` increased the fresh compact geographic error by **70.89 m**. Conditional RF RMS rose by 0.0653 Hz and the frequency score rose from 33,820.243 to 33,821.523.

## Host timing

The raw workers used CPUs 0, 1 and 6–11 on an Intel Core Ultra 9 285K. Each had a 512 MiB charged memory cap and zero swap. They authenticated 8.182 GB of compressed data and 10.834 GB of decoded IQ from a 299.977-second recording. Together they used 3,134.03 resident detector CPU seconds and 3,159.53 cgroup CPU seconds between bound worker start and finish. Largest worker RSS was 217.10 MiB and the highest charged peak was 512 MiB. The simultaneous raw service allowance was 720 seconds. [Worker receipts](receipts/) · [Per-visit timings and RF ordinals](timing.csv) · [Timing figure](timing.pdf)

| Valid-visit detector clock | P50 (ms) | P95 (ms) | P99 (ms) | Maximum (ms) | At or under 20 ms |
|---|---:|---:|---:|---:|---:|
| Resident CPU | 432.56 | 1,186.34 | 1,312.81 | 2,070.23 | 0 / 6,727 |
| Resident wall | 476.99 | 1,315.00 | 2,726.00 | 14,610.86 | 0 / 6,727 |

The maximum CPU visit was 1,306, RF channel 3 ordinal 163. The maximum wall visit was 4,679, RF channel 8 ordinal 584, and used 344.09 ms of CPU. The same-visit comparison with the scalar-pruned path comes from the separately qualified held acquisition assay. Its four DS29-0519 windows yielded a 22.92 ms paired median detector CPU saving over 20 timing pairs, or 7.97%. The complete-waveform results give absolute clocks for the batched path. [Held timing comparison](../fine-batch/summary.json)

| Independent compact service, both arms | Wall (s) | Cgroup CPU (s) | Charged peak (MiB) | Swap |
|---|---:|---:|---:|---:|
| Fresh factors, CPU 0 | 50.29 | 48.39 | 302.71 | 0 |
| Archived factors, CPU 1 | 49.90 | 48.42 | 298.71 | 0 |

Fresh raw launch through returned coordinates took **633.39 seconds**, including archive verification, factor assembly and fit dispatch. The earlier complete fast four- and five-region runs recorded 188 and one of 6,727 valid detector calls at or under 20 ms wall, respectively. Their compact position stages took 104.64 and 75.78 seconds wall. These are separate measurements on fast detector outputs from the same saved input. [Fresh fit receipt](receipts/actual/terminal.json) · [Archive fit receipt](receipts/archive/terminal.json) · [Earlier complete fast resources](../../latency-and-support/complete-timing/resources.csv)

## Reproduce

Use an unpublished evidence checkout to freeze a new plan. For a replay of the published plan, copy the source lock into a new local work directory and pass the directory to the remaining commands. Keep the signed inputs and releases at the absolute paths in the lock.

```bash
.venv/bin/python -m tools.pipeline_eval.qualification.batched_waveform freeze
.venv/bin/python -m tools.pipeline_eval.qualification.batched_waveform preflight
.venv/bin/python -m tools.pipeline_eval.qualification.batched_waveform run
.venv/bin/python -m tools.pipeline_eval.qualification.batched_waveform_results position
.venv/bin/python -m tools.pipeline_eval.qualification.batched_waveform_results publish
```
