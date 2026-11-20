# Exact lane peak selector on DS26-0237

Changing only the score-map peak selector cut detector CPU by **15.0%** on the complete 299.98-second lower-edge recording. All **60,306 ordered candidates** matched the prepared replay and the original capture archive. The fresh position matched the prepared run with **353 m** error at `c = 0` and **262 m** with fitted `c`. Eight workers took **458.58 seconds** to replay the IQ, and **0 of 6,766** valid visits completed the dual-antenna detector within 20 ms. [Source lock](source-lock.json) · [Audit](audit.json) · [Independent interleaved selector benchmark](../prepared-hotpath/README.md)

## Native fidelity

All 106 compressed chunks authenticated. The recorder delivered 6,768 visits, including two original capture exclusions. The UTC anchor, delivery clocks and final sample counter match the original capture. All 13,532 physical probe rows match both references byte for byte in canonical form. They contain 10,243 passing candidates on 3,740 probes, with zero gate changes. The fresh stream carries the updated detector source identity. [Fresh native stream](native.json.gz) · [Comparison](comparison.json) · [Three matched launch checks](receipts/smoke.json)

## Position and RF calibration

The compact solver ran separately on the new factors and the original capture archive. Both used the original 25 km offer, 47 causal TLE snapshots, and the same candidates, priors and search budgets. Both fresh fits and the earlier prepared fit returned identical coordinates and frequency diagnostics in each calibration arm. [Per-arm scores](scores.csv) · [Chart for `c = 0`](charts/c0/modifications.pdf) · [Chart for fitted `c`](charts/fitted_c/modifications.pdf)

| Position input | Error at `c = 0` (km) | Error with fitted `c` (km) | Conditional RF RMS, zero / fitted (Hz) |
|---|---:|---:|---:|
| Fresh lane-selector IQ replay | 0.3531 | 0.2619 | 80.670 / 80.608 |
| Earlier prepared IQ replay | 0.3531 | 0.2619 | 80.670 / 80.608 |
| Original capture archive, fresh compact solve | 0.3531 | 0.2619 | 80.670 / 80.608 |
| Earlier four-region IQ replay | 0.3816 | 0.3230 | 92.538 / 92.427 |
| Earlier fifth-region IQ replay | 0.2186 | 0.1786 | 93.715 / 93.645 |
| Original v5, all four reference roles | 0.3618 | 0.2714 | 102.89 / 91.74 |

At this surveyed site, fitted `c` reduced the selector run's position error by 91.1 m. Conditional RF RMS fell by 0.062 Hz and the frequency objective moved from 32,111.050 to 32,111.940. Each geographic error was within 5% of all four matched original v5 roles. [Both calibration outputs](receipts/actual/position.json) · [Matched endpoints](comparison.json)

## Host timing

Both runs replayed the same raw chunks on CPU cores 0–7 of an Intel Core Ultra 9 285K. Detector timing starts with resident CI16 and includes acquisition, refinement and projection for both physical receivers. Raw elapsed time also includes reading, decompression, authentication and shard output. The runs took place at different times on a shared host. Median detector wall fell by 40 ms and 95th-percentile wall rose by 108 ms. [Per-visit paired timings](paired-timing.csv) · [Timing chart](timing.pdf) · [Cache ledger](cache.csv)

| Measurement | Prepared detector | Prepared + lane selector |
|---|---:|---:|
| Raw replay elapsed, seconds | 483.71 | 458.58 |
| Eight raw workers, cgroup CPU seconds | 2,937.31 | 2,500.74 |
| Dual detector, CPU seconds | 2,914.74 | 2,477.59 |
| Folded grids and their input preparation, CPU seconds | 923.16 | 951.26 |
| Remaining detector work, CPU seconds | 1,991.58 | 1,526.34 |
| Detector CPU, median / P95 (ms) | 372.14 / 624.78 | 315.30 / 540.53 |
| Detector wall, median / P95 (ms) | 384.95 / 857.69 | 344.75 / 966.19 |
| Valid visits within 20 ms detector wall | 0 / 6,766 | 0 / 6,766 |
| Compact position, CPU / wall seconds | 48.19 / 50.37 | 50.01 / 50.35 |
| Raw launch through coordinates, elapsed seconds | 540.81 | 514.09 |

Complete detector CPU improved by a paired median of 60.74 ms per visit. The lane selector run still used 8.26 detector CPU seconds per second of recorded data. The peak worker RSS and cgroup memory charge were 205.50 MiB and 457.48 MiB, respectively, with zero swap. Both runs executed 15,330 full grids. The fresh position service used 15.32 seconds of wall time for native preparation and 34.0 seconds across the measured solve stages. Re-solving the archived factors took 51.25 seconds wall on its own capped worker. [Worker receipts](receipts/) · [Matched timing summaries](comparison.json) · [Prior prepared replay](../../original-support/prepared-waveform/README.md)

## Reproduce the replay

Run these commands from the repository root with the recorded corpus and releases named in the frozen source lock. The freeze step is for an unpublished evidence directory. For a repeat with this sealed input, copy `source-lock.json` to a new work directory and pass that directory to `preflight`, `run`, and `position`. The raw and position evidence stays in the chosen work directory. [Source lock](source-lock.json) · [Executed raw worker commands](receipts/launch.json) · [Protocol](PROTOCOL.md)

```bash
.venv/bin/python -m tools.pipeline_eval.qualification.selector_waveform freeze
.venv/bin/python -m tools.pipeline_eval.qualification.selector_waveform preflight
.venv/bin/python -m tools.pipeline_eval.qualification.selector_waveform run
.venv/bin/python -m tools.pipeline_eval.qualification.selector_waveform_results position
.venv/bin/python -m tools.pipeline_eval.qualification.selector_waveform_results publish
```
