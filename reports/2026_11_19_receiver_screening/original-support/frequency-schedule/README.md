# Full-pass RF lanes and equal-call bursts on original capture factors

The compact receiver published both arms for all eight two-lane and all eight four-lane inputs. It withheld every count-matched two-lane-budget burst input and five of eight four-lane-budget burst inputs. Yet at the DS29-0082 timing anchor, retaining two or four RF lanes for the entire pass still moved fitted error from **0.516 km with all factors to 15.161 and 15.325 km**. This separates the ability to build curved tracks from the geometry needed for an accurate fix. [Position figures](charts/README.md) · [Full scores](scores.csv)

The frozen roster includes DS29-0082 as the detector-cost anchor and DS26-0162 as the raw-waveform overlap. The six metadata-hash holdouts are DS26-0185, DS26-0315, DS26-0088, DS29-0316, DS29-0604 and DS29-0174. Each whole-lane input keeps every available visit on the predetermined complementary RF lanes. Its paired burst input spends the same calls in each of fifteen delivery-time bins, spread across available RF lanes with one contiguous block per RF and bin. All variants retain both physical receiver slots, original clocks, causal catalogue, original request and full recorded time horizon. [Protocol](PROTOCOL.md) · [Prospective plan](plan.json) · [Visit schedules](schedule.json)

## Geographic results

Each divided entry lists `c = 0` / fitted `c`. Quantiles use numerical endpoints, with publication counts shown to preserve the scheduled denominator. The original v5 allowance uses the archive's no-repair error on each matched recording.

| Input | Published among eight | Panel median, km | Panel P95, km | Within 10% of original v5 | Held-six median, km |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full original factors | 8 / 8 | 0.928 / 0.920 | 1.958 / 1.759 | 8 / 8 | 0.988 / 0.966 |
| Two complete RF lanes | 8 / 8 | 1.947 / 1.947 | 11.307 / 11.311 | 3 / 3 | 1.622 / 1.622 |
| Same-count two-lane-budget bursts | 0 / 0 | — | — | 0 / 0 | — |
| Four complete RF lanes | 8 / 8 | 1.246 / 1.210 | 10.963 / 10.986 | 4 / 3 | 0.719 / 0.718 |
| Same-count four-lane-budget bursts | 3 / 3 | 7.010 / 6.646 | 8.053 / 7.882 | 0 / 0 | 7.010 / 6.646 |

Four full lanes lowered the six-held fitted median from 0.966 to 0.718 km and raised the fitted P95 from 1.871 to 2.917 km. The 41 services returned terminal results, including 13 geographic withholdings. Conditional RF and error differences are recorded separately from support and all four original v5 options. [Paired position and RF changes](effects.csv) · [Original v5 positions and RF](capture-era-v5.csv) · [Support census](support.csv)

On DS26-0162, the fixed staggered quarter used 1,675 calls and produced **1.286 / 1.180 km**, compared with 1.639 / 1.640 km for two complete RF lanes at 1,691 calls. The corresponding equal-call burst was withheld. The exact same staggered factor array was also generated independently from actual saved IQ. The decoded probes, exposures, clocks and exclusions agree exactly. Both arm outputs, conditional RF and frequency objectives reproduce exactly across both conditional inputs and the full original comparator. [Native overlap lock](overlap-native-lock.json) · [Position parity](overlap-parity.json) · [Independent waveform evidence](../scheduled-waveform/)

## Detector work and paced completion

On DS29-0082, the chosen two full lanes have 835 valid visits, 17.2% of the 4,868 actual valid opportunities. The four lanes have 2,327. Their corresponding bursts retain the same count in each time bin. The table uses measured per-visit process CPU from the exact capture-era detector, applied to an ideal independent-worker FIFO at the original arrival times. The simulated detector readiness is separate from the measured compact position phase. Full-stream positions wait for the acquisition clock and the detector to finish.

| Anchor input | Selected measured CPU work | Calls ready by 300 s | Worker cores | Simulated detector ready | Measured position phase |
| --- | ---: | ---: | ---: | ---: | ---: |
| Two complete RF lanes | 490.21 s | 835 / 835 | 2 | 299.96 s | 19.45 s |
| Same-count bursts | 507.69 s | 833 / 835 | 2 | 300.29 s | 1.89 s, withheld |
| Four complete RF lanes | 1,397.59 s | 2,324 / 2,327 | 6 | 300.42 s | 28.81 s |
| Same-count bursts | 1,432.60 s | 2,327 / 2,327 | 6 | 299.31 s | 1.36 s, withheld |
| Full original factors | 3,035.04 s | 4,788 / 4,868 | 10 | 304.13 s | 50.04 s |
| Full original factors | 3,035.04 s | 4,859 / 4,868 | 12 | 300.70 s | 50.04 s |

The timing model excludes I/O, detector setup and contention and makes no individual 20 ms compliance claim. The actual DS29-0082 complete saved-IQ detector ran in 498.13 s on ten host workers. The independent DS26-0162 staggered saved-IQ detector took 192.45 s on six workers and 855.18 process CPU seconds. Transferring the anchor mean predicts 1,044.31 CPU seconds for those same 1,675 nominated visits, 22.1% higher than measured. The other transferred budgets are scenario estimates. [Measured timing authority](../../antenna-confirmation/capture-whole/README.md) · [All paced core counts](pacing.csv) · [Exact anchor frontier](frontier.pdf)

Fresh full-input compact service times ranged 50.0–161.6 s, with median 90.2 s. The two- and four-lane position phase medians were 31.3 and 40.1 s. The largest observed charged peak was 471.5 MiB with zero swap. These are stored-factor-to-terminal resource measurements under the installed package. [Resources](resources.csv)

## Reproduction

Run `python -m tools.pipeline_eval.qualification.frequency_schedule_trial /path/to/new/local/work` from a checkout with the authenticated source archives and no existing plan. After the terminal lock, run `python -m tools.pipeline_eval.qualification.frequency_schedule_results /path/to/work --plot /path/to/plots`. The two budget figures include the six independently selected holdouts separately from the full eight. [Terminal prediction lock](prediction-lock.json)
