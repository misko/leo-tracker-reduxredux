# Original capture detector replayed from saved IQ to position

The combined FFT implementation reproduced every original native observation on DS29-0082 and returned a position within **5% of the original no-repair v5 error in both calibration arms**. The native detector took 498.13 seconds across ten host workers. No valid visit met the 20 ms wall budget. This is a full recording at one known roof offer. The recording was selected for its authenticated installed release, complete waveform and causal request, and 4,868 valid visits. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json) · [Prediction lock](prediction-lock.json)

## Capture fidelity

The workers authenticated all 106 compressed chunks and 6,772 scheduled visits, including 1,904 exclusions. The original 6,772 delivery-clock records, UTC anchor, final sample counter, physical receiver order and exclusion details matched exactly. All **9,736 physical probe rows and 42,162 ordered candidate records** were byte-identical in canonical encoding. The original 4,582 strict gate passes on 1,868 probes were reproduced with zero changed gates. The fresh native document carries its own verified binary and replay provenance. The batch FFT uses binary32 for correlations, and the earlier grid audit measured small differences before candidate selection. [Full factor audit](audit.json) · [Fresh native output](native.json.gz) · [Prior coarse-grid audit](../capture-exact/grid-audit.json)

## Position

Two independently started compact services consumed the fresh factors and original archived factors respectively, with the same causal catalogue and original 25 km region. Their unrounded coordinates, conditional RF RMS and frequency scores were identical in both arms. The earlier wide four- and five-region services came from complete saved-IQ replays on the same recording and request. [c = 0 error chart](charts/c0/modifications.pdf) · [Fitted-c error chart](charts/fitted_c/modifications.pdf) · [Per-arm scores](scores.csv)

| Input and solver | c = 0 geographic error (km) | Fitted-c geographic error (km) | Conditional RF RMS, c = 0 / fitted (Hz) |
|---|---:|---:|---:|
| Fresh capture-era IQ → compact | 0.5681 | 0.5158 | 97.00 / 96.68 |
| Archived original capture factors → compact | 0.5681 | 0.5158 | 97.00 / 96.68 |
| Earlier stock wide four-region IQ → compact | 2.4892 | 2.3457 | 84.42 / 84.25 |
| Earlier wide fifth-region IQ → compact | 1.7350 | 1.7571 | 89.61 / 89.25 |
| Original v5 no-repair | 0.5669 | 0.5172 | |
| Original v5 selective gap | 0.5669 | 0.5172 | |
| Original v5 omitted-track-one | 0.1154 | 0.4862 | |
| Original v5 omitted tracks | 0.1154 | 0.4862 | |

Fitted `c` reduced the fresh capture error by 52 m on this recording. The wide controls had lower conditional RF RMS and larger geographic errors.

## Host replay cost

The original acquisition used 299.997 seconds of recorded delivery time. The replay read 8.40 GB compressed and authenticated 10.84 GB of decoded IQ. Across 4,868 valid visits it invoked the complete folded FFT grid 10,875 times. The total was 3,035.22 detector CPU seconds and 3,058.87 CPU seconds between the workers' bound start and terminal snapshots. The largest individual charged peak was 512 MiB and the largest detector process RSS was 211 MiB. Each raw worker had its own 512 MiB zero-swap limit. The fresh compact service ran both calibration arms in 27.56 seconds with 278 MiB charged peak and zero swap. The host was an x86-64 Intel Core Ultra 9 285K. [Per-visit timing](timing.csv) · [Timing chart](timing.pdf) · [Worker and position receipts](receipts/)

| Detector replay | Measured CPU P50 / P95 (ms per valid visit) | Wall P50 / P95 (ms per valid visit) | At most 20 ms wall |
|---|---:|---:|---:|
| Complete capture-era combined | 600 / 1,197 | 634 / 1,550 | 0 / 4,868 |
| Earlier wide four-region | 25.6 / 30.9 | 26.0 / 35.0 | 38 / 4,868 |
| Earlier wide fifth-region | 30.2 / 36.8 | 30.6 / 38.8 | 0 / 4,868 |

The candidate's aggregate detector CPU alone is about 10.1 times the recording duration on this host. The ten-worker run measures laboratory throughput with independent memory budgets. Wide host timings come from separate services under earlier load. [Earlier complete timings](../../latency-and-support/complete-timing/resources.csv)

Regenerate both error charts from the sealed results with the standard renderer.

```bash
python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/antenna-confirmation/capture-whole \
  --out /var/tmp/capture-whole-charts
```
