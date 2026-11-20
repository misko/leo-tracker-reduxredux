# Position from two detectors running on the recorded clock

The four-region search can return many more measurements than the original GLRT during a recording. We tested two ways to use both receivers. The replacement rule takes the original two-antenna measurement whenever it arrives by the end of the recording. The fill rule keeps every fast positive and uses the original to fill a missed antenna. A third comparison requires each measurement to arrive within 20 ms of its own scheduled visit. The position solver saw only the packets available by its declared cutoff. Both calibration settings use the same observations, original region, candidate roster and solver budget. [Prespecified rules](PROTOCOL.md) · [Candidate selections and clocks](support.csv)

Both host detectors received the same previously recorded I/Q windows, hardware exclusions and arrival clock. Each used one pinned core and one waiting visit. The source read the capture once into a separately measured stage. We closed the position input at the last scheduled arrival. This discards one late fast result and two late original results per recording. Solver clocks start after the cutoff. The two roof recordings had earlier whole-waveform results, so this comparison measures the effect of actual delivery and packet choice on those known recordings. [Acquisition receipt](../parallel-acquisition/manifest.json) · [Position runtime per run](timing.csv)

| Policy | DS26-0237 error km, zero / fitted | DS29-0082 error km, zero / fitted | Within +10% of v5 or better, zero / fitted |
| --- | ---: | ---: | ---: |
| Original v5, no repair or selective gap | 0.362 / 0.271 | 0.567 / 0.517 | 2/2 · 2/2 |
| Original v5, one or two tracks omitted | 0.362 / 0.271 | 0.115 / 0.486 | 2/2 · 2/2 |
| Fast only | 0.491 / 0.534 | 3.545 / 3.480 | 0/2 · 0/2 |
| Original only, using results available by close | Withheld | Withheld | 0/2 · 0/2 |
| Replace the pair on overlap | 0.511 / 0.530 | 2.303 / 2.288 | 0/2 · 0/2 |
| Fill a missed antenna | 0.249 / 0.268 | 2.409 / 2.329 | 1/2 · 1/2 |
| Require delivery within 20 ms per visit | 1.284 / 1.136 | 5.249 / 5.189 | 0/2 · 0/2 |

Filling missed antennas improved both fixes relative to the concurrent fast-only branch. Its DS26 fix also met the +5% v5 allowance in each calibration arm. Adding original detections to already-returned fast pairs supplied 33 passing antenna measurements on DS26 and 26 on DS29. In total the fill rule also admitted 39 and 104 extra visits through the original worker. The DS29 fix stayed more than four times the no-repair v5 fitted error. With the 20 ms rule, the lowest DS29 fitted RF residual of these policies, 87.4 Hz, coincided with the largest position error. [Every geographic and RF score](scores.csv) · [Fitted fill distribution](charts/fitted_c/parallel-concurrent-fill.png) · [Zero-calibration distribution](charts/c0/parallel-concurrent-fill.png)

After the approximately 300 s acquisition cutoff the fill fit took another 116.5 s on DS26 and 47.7 s on DS29. Both are host service measurements. Each original-only fit reached its withholding decision, after 19.2 s or 1.3 s. Each case had one measured simultaneous acquisition run. The separately timed development run below shows how much the DS29 result can move when the admission schedule changes.

A separate development check aligned two independently measured DS29-0082 service traces to the recording clock. The fast-only fitted error was 2.340 km. Filling a missed antenna increased it to 3.297 km and replacing whole pairs increased it to 3.895 km. The original-only branch withheld. Four fast packets met the 20 ms deadline, all without a positive pilot, so the receiver explicitly withheld under the strict deadline. These traces model the combination of two separate runs. [Development distributions](separate-clocks/charts/index.html) · [Development scores](separate-clocks/scores.csv)

Repeating that development comparison into fresh work and result directories reproduced its support table and all ten calibration-specific score rows byte for byte. The acquisition check independently matched every before-cutoff antenna packet and hardware clock against the simultaneous workers' saved outputs. [Acquisition evidence](../parallel-acquisition/README.md)

## Reproduce

The single-command `benchmark --receiver receiver-deadline` rebuilds all chart pages from the sealed data, including v5 no repair, selective gap, one omitted track and two omitted tracks. At a checkout with the authenticated recording and compact receiver resources, the following commands repeat the numerical fits and then score them. Supply an unused scratch directory and a separate new result directory. Append `--separate-clocks` to both commands for the development check.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.parallel_position "$unused_work_directory" --out "$new_result_directory"
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.parallel_position_results --out "$new_result_directory"
```
