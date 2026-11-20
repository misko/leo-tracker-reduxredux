# RF-aware waiting during the original DS29-0082 replay

The recorded delivery clock runs for five minutes. The original dual-GLRT detector on CPU12 has one dispatch and one waiting slot. When a new valid arrival finds both occupied, it replaces the waiter only when the incoming physical RF was started earlier. An unseen RF has precedence and exact ties retain the first waiter. Hardware-invalid arrivals never update the queue. Arrival decisions, actual service starts, and ordered retirement are independently recorded.

The fit consumes the actual native packets emitted by that service. Each packet is compared against the independent full original detector replay. Delivery clocks and hardware exclusions retain the full recording authority. The counterpart is the separately executed original FIFO on CPU10, using the same read-only predecoded source and original arrival clock. The staged source lives outside each 512 MiB, zero-swap receiver service. These are host timings.

The RF-aware run emitted 370 of 4,868 hardware-valid visits, with 44–48 visits per RF channel. It rejected 4,003 incoming visits and displaced 495 waiters. All 1,904 hardware-invalid arrivals retained their original status. The 370 emissions supplied 132 gated receiver probes across 95 visits. The recorded-arrival service used 301.75 s elapsed and 293.60 CPU seconds, including 285.65 detector CPU seconds, with a 263 MiB cgroup peak. Median and P95 arrival-to-emission ages were 1.279 and 2.174 s, and zero emissions met 20 ms. The separately charged staged waveform held 10.84 GB of source I/Q.

The actual compact fit returned `no_active_curvature` in both calibration arms after 4.94 s. It returned no position and no frequency-fit score. The frozen measured-service forecast chose 497 visits. The live worker emitted the 370 verified packets described above, and only those packets reached this fit.

| Actual queue | Valid visits emitted | Emitted per RF channel | Gated receiver probes | P50 / P95 age |
| --- | ---: | ---: | ---: | ---: |
| Original FIFO, CPU10 | 387 | 19–74 | 151 | 1.361 / 2.216 s |
| Oldest RF, CPU12 | 370 | 44–48 | 132 | 1.279 / 2.174 s |

Both runs received all 6,772 scheduled arrivals and used the same original detector and delivery clock on separate host cores. RF replacement made the per-channel counts more even and retained 17 fewer valid visits and 19 fewer gated probes. The independent FIFO service used 302.08 s elapsed and 298.38 CPU seconds. Both runs had zero emissions within 20 ms.

Both actual compact fits withheld both positions with `no_active_curvature`. All four capture-era v5 options returned positions on the full original factors. Their geographic errors span 0.115–0.567 km at `c = 0` and 0.486–0.517 km with fitted `c`. The [paired position charts](charts/README.md) include both calibration arms and the four original options. The measured channel support and queue accounting are shown in the [stage figure](stage.pdf).

## Evidence

- `source-lock.json`, `events.json.gz`, and `PROTOCOL.md` define the original measurement. `raw/trace.json.gz` contains chronological terminal visits and actual emitted packets. `raw/admission.json.gz` contains every arrival decision and the observed start clocks used in contested admissions.
- `raw-prediction-lock.json` binds the live services and their summaries. `prediction-lock.json` separately binds the genuinely refit compact positions. The paired position chart uses the independently sealed original FIFO results and the four historical v5 options in both calibration arms.
- `resources.csv`, `rf-support.csv`, `geographic.csv`, and `frequency-fit.csv` report separately measured cost, RF coverage, position error, and frequency fit.

The qualification entry points are `python -m tools.pipeline_eval.qualification.paced_rf run` and `python -m tools.pipeline_eval.qualification.paced_rf_results measure`. They use the frozen cadence source and start actual receiver services. Run `python -m tools.pipeline_eval.qualification.paced_rf_results publish` to recheck the completed sources and draw the figures without running radio or compact work.
