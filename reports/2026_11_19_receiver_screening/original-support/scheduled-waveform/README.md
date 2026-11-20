# Original acquisition on a staggered quarter schedule

DS26-0162 was selected before scoring for the smallest valid workload among three remaining complete, qualified capture releases. This prototype ran the full original dual-antenna detector on every fourth visit per signed RF lane, with a channel-dependent offset. It retained all eight lanes, both physical receivers at every selected visit, the original clock inventory and the original causal inputs and 25 km offer. [Protocol](PROTOCOL.md) · [Frozen source and schedule](source-lock.json)

The replay processed 1,675 of 6,713 valid visits, 75.05% fewer detector calls than processing every valid visit. It authenticated all 6,772 recorded visits. The 5,038 valid policy omissions retained empty physical probe slots, and all 59 hardware exclusions retained their original reasons and clocks. Eighteen hardware exclusions fell on scheduled detector visits. Each RF lane contributed 198–212 valid measured visits, with the longest observed gap between measurements 4.26 seconds. [Per-visit ledger](timing.csv) · [Native and clock audit](audit.json)

An independent archive projection matched all 13,426 physical probe rows, 15,898 ordered retained candidate records and 4,410 strict candidate gates byte for byte. The schedule retained 1,401 of the original 5,517 gate-positive receiver probes. [Fresh native data](native.json.gz) · [Prediction lock](prediction-lock.json)

| Position input | `c = 0` geographic error (km) | Fitted `c` geographic error (km) | Conditional RF RMS, `c = 0` / fitted (Hz) |
|---|---:|---:|---:|
| Actual quarter-scheduled IQ through compact | 1.2858 | 1.1798 | 72.97 / 73.00 |
| Full original archived factors through fresh compact | 0.4015 | 0.4167 | 47.47 / 47.46 |
| Original v5 no-repair | 0.3988 | 0.4150 | |
| Original v5 selective gap | 0.3988 | 0.4150 | |
| Original v5 omitted-track-one | 0.4033 | 0.4206 | |
| Original v5 omitted tracks | 0.4033 | 0.4206 | |

Both compact services published both calibration arms. The scheduled replay missed the 5% and 10% limits relative to original no-repair v5 in both arms. The full-factor control met both limits in both arms. [c = 0 chart](charts/c0/modifications.pdf) · [Fitted-c chart](charts/fitted_c/modifications.pdf) · [Scores](scores.csv)

The raw pass took 192.45 seconds across six independent workers with 512 MiB and zero swap per worker. It used 855.18 detector CPU seconds and 876.89 aggregate worker CPU seconds. On selected valid visits, detector CPU P50/P95 were 441/766 ms, wall P50/P95 were 469/1,075 ms, and zero visits met 20 ms. The fresh scheduled compact fit took 36.35 seconds at 353 MiB charged peak. The full-factor control took 86.21 seconds at 372 MiB. The raw replay still decoded and authenticated all waveform bytes. The raw timings apply to this host, and the full original factor control starts after detection. [Timing chart](timing.pdf) · [Service receipts](receipts/)
