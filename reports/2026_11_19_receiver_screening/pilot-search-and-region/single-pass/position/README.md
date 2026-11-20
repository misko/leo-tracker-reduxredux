# Primary-only original GLRT on DS26-0237

Removing the original 22-anchor retry eliminated 1,613 FFT grids and 448 positive receiver probes on the complete 299.98-second DS26-0237 recording. Survey error increased from **0.353 to 0.889 km** at `c = 0` and from **0.262 to 0.780 km** with fitted `c`. [Source lock](source-lock.json) · [Audit](audit.json)

## Physical observations

The original producer ran a 12-anchor acquisition on each receiver. It retried a receiver with 22 anchors when that receiver's primary failed the fractional gate and the other receiver's primary passed. The full selector replay's measured inverse FFT counts distinguish the 12-anchor and 22-anchor grids, including repeats caused by the conditioned-CFO tie guard. The census identified 1,592 retry visits among 6,766 valid visits. Twenty-one retry visits used two 22-anchor grids because of the tie guard. [Prior complete selector replay](../../../receiver-deadline/selector-waveform/README.md) · [Frozen grid census](source-lock.json)

The replay recomputed both receiver rows on all 1,592 original retry visits from authenticated saved CI16. It used the complete conditional replay's existing measurements on 5,174 no-retry visits. All 106 compressed chunks authenticated. The resulting stream preserves the original clock anchor, delivery clocks, last sample counter, receiver order, and two physical exclusions. The preflight covered 13 held no-retry visits and both physical retry directions. A separate assay also reproduced every conditional and primary result on its 20 DS26-0237 visits, including five rescued visits. [Preflight](receipts/smoke.json) · [Independent assay receipt](receipts/independent-DS26-0237.json.gz) · [Complete native stream](native.json.gz)

| Detector policy | Physical probes | Candidates | Rejected candidates | Gate passes | Positive probes |
|---|---:|---:|---:|---:|---:|
| Primary-only 12 anchors | 13,532 | 59,977 | 50,583 | 9,394 | 3,292 |
| Original conditional 12/22 anchors | 13,532 | 60,306 | 50,063 | 10,243 | 3,740 |
| Full wide four-region | 13,532 | 63,443 | 46,099 | 17,344 | 4,008 |
| Full wide five-region | 13,532 | 64,028 | 45,502 | 18,526 | 4,446 |

Exactly 11,940 rows match the conditional output, including the initially successful receiver at every retry visit. The 448 changed positive probes all lost their gate pass, and 849 fewer candidates passed in aggregate. [Per-probe comparison](changed-visits.csv) · [Full wide input bindings](audit.json)

## Position and RF calibration

Both calibration arms used the same primary observations, causal catalogue, 25 km offer, candidates, priors and compact search budget. The compact solve accepted 3,292 observations on 89 tracks, compared with 3,740 observations on 103 tracks for the full conditional detector. The predictions were sealed before the publisher read the survey reference. [Prediction lock](prediction-lock.json) · [Score lock](score-lock.json) · [Coordinates and solve receipt](receipts/actual/position.json)

| Detector or v5 control | Survey error, `c = 0` (km) | Survey error, fitted `c` (km) | Conditional RF RMS, zero / fitted (Hz) |
|---|---:|---:|---:|
| Primary-only 12 anchors | 0.8889 | 0.7797 | 77.715 / 77.700 |
| Original conditional 12/22 anchors | 0.3531 | 0.2619 | 80.670 / 80.608 |
| Full wide four-region | 0.3816 | 0.3230 | 92.538 / 92.427 |
| Full wide five-region | 0.2186 | 0.1786 | 93.715 / 93.645 |
| Original v5 baseline | 0.3618 | 0.2714 | 102.892 / 91.742 |
| Original v5 selective-gap | 0.3618 | 0.2714 | 102.892 / 91.742 |
| Original v5 omitted-track-one | 0.3618 | 0.2714 | 102.892 / 91.742 |
| Original v5 omitted-tracks | 0.3618 | 0.2714 | 102.892 / 91.742 |

On the primary-only observations, fitting `c` lowered conditional RF RMS by 0.015 Hz, moved the frequency score from 25,260.710 to 25,263.280, and reduced survey error by 109 m. Across detector policies the primary-only stream had lower RMS and lay 536 m farther from the survey point at `c = 0` and 518 m farther with fitted `c`. The frequency scores across policies summarize different sets of observations. [Per-arm scores](scores.csv) · [Original v5 controls](v5-controls.csv) · [`c = 0` chart](charts/c0/modifications.pdf) · [Fitted `c` chart](charts/fitted_c/modifications.pdf)

## Host timing

The selected replay used four capped workers on CPUs 12–15 and took **259.37 s** elapsed. The 1,592 measured dual-receiver detector calls consumed **927.04 CPU s**. The four workers used 959.40 cgroup CPU seconds including data access, authentication and output. The maximum worker RSS was 199.38 MiB and the cgroup peak was 512 MiB with zero swap. [Raw launch](receipts/launch.json) · [Service exits](receipts/raw-exits.json) · [Timing chart](timing.pdf)

| Detector timing | Historical conditional | Measured primary-only |
|---|---:|---:|
| Retry visits timed | 1,592 | 1,592 |
| Detector CPU, median / p95 (ms) | 511.77 / 672.39 | 563.51 / 796.41 |
| Detector wall, median / p95 (ms) | 537.89 / 1,489.66 | 568.93 / 841.98 |
| Detector CPU, summed (s) | 840.86 | 927.04 |
| Complete factor stream, dense FFT grids | 15,330 | 13,717 |

The archived conditional run used performance cores 0–7. This run used efficiency cores 12–15. A separate same-core assay timed three held retry visits for five interleaved repetitions each and found a median saving of 707.66 CPU ms per visit. The full conditional replay recorded 2,477.59 detector CPU seconds. Combining 1,636.74 archived nonretry CPU seconds with 927.04 newly measured retry CPU seconds gives a cross-execution accounting estimate of 2,563.78 CPU seconds, or 640.95 seconds under ideal four-core division. The old full conditional CPU total divided by four is 619.40 seconds. These cross-core calculations describe timing receipts from separate executions. The selected primary run had zero visits with a detector wall time at or below 20 ms. [Per-visit timing](timing.csv) · [Same-core assay](receipts/independent-DS26-0237.json.gz)

The compact service ran both calibration arms in 67.37 wall seconds, including 20.26 seconds of native preparation. It used 66.56 cgroup CPU seconds and peaked at 304.62 MiB with zero swap. [Compact service receipt](receipts/actual/terminal.json) · [Resource receipt](receipts/actual/end.json)

## Reproduce

Run from the repository root with the pinned capture, producer, libraries, inputs and compact receiver installed. Use a new local work directory and reserve the four raw cores named in the source lock. CPU 22 was used for the standalone launch checks. The replay reads saved IQ through the original recording adapter under the `leo` account. The first launch check encountered a report-only dependency imported into the capture environment. The corrected replay moved that import to source verification and froze a new work directory. A fresh-directory launch check reproduced all 15 saved-IQ hashes, gate attempts and conditional and primary probe digests. [First launch receipt](receipts/preflight-a/service.log) · [Repeat launch check](rerun-lock.json) · [Protocol](PROTOCOL.md)

```bash
source=reports/2026_11_19_receiver_screening/pilot-search-and-region/single-pass/position
work=$(mktemp -d /srv/bulk/leo-dev/primary-replay.XXXXXXXX)
chmod 0755 "$work"
install -m 0644 "$source/source-lock.json" "$source/receipts/smoke-input.json" "$work/"
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_position preflight "$work" 22
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_position run "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_position_results position "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.single_pass_position_results publish "$work" --output "$work/report"
```
