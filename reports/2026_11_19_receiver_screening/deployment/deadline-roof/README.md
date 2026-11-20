# Post-capture deadlines on 159 DS26 roof recordings

The **180-second model published 151/159** fixes in each arm, two more than archived compact alone. Its fitted-(c) P95 position error was **4.233 km**, versus **3.541 km** for compact. The 30- and 90-second models behaved mostly like smooth clock after waiting for compact. [Two-arm chart gallery](charts/index.html) · [All recording and route rows](scores.csv)

The same operational router assigns compact the total allowance minus 15 seconds. It returns an on-time compact position or explicit scientific withholding. A compact numerical failure or timeout passes the remaining allowance to smooth clock. The model uses the recorded individual worker intervals, including historical timing and confirmation fields where appropriate. It compares complete stored GLRT factors under the same causal catalogue and supplied roof tile. [Predefined protocol](PROTOCOL.md) · [Source and roster bindings](plan.json)

| Position policy | Published per arm | Compact / smooth publications | `c=0` median / P95 (km) | Fitted `c` median / P95 (km) | Fitted within 10% of original v5 / paired | Median / P95 post-capture elapsed (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 s total | 133/159 | 0 / 133 | 1.538 / 4.438 | 1.382 / 4.509 | 48/124 | 21.29 / 24.93 |
| 90 s total | 135/159 | 6 / 129 | 1.538 / 4.474 | 1.413 / 4.774 | 50/124 | 81.15 / 84.79 |
| 180 s total | 151/159 | 124 / 27 | 1.102 / 4.343 | 1.105 / 4.233 | 121/139 | 125.29 / 172.45 |
| Standalone archived compact | 149/159 | 149 / 0 | 0.990 / 3.545 | 1.014 / 3.541 | 138/142 | 125.05 / 198.14 |
| Standalone archived smooth clock | 135/159 | 0 / 135 | 1.579 / 4.474 | 1.413 / 4.780 | 48/125 | 6.29 / 9.93 |

The two standalone controls keep their recorded archive outcomes and caps. Published-error percentiles use each policy's own fixes. Every policy has an all159 publication denominator. Paired proximity requires a position from both the policy and original no-repair v5 for the same case and arm. The `c=0` paired counts are 40/124, 43/124 and 119/139 at 30, 90 and 180 seconds. [Full distributions and both-arm score counts](summary.json)

At 30 seconds, all 158 supported inputs reach compact's 15-second cutoff. Smooth clock then withholds 23 and times out on two. The 90-second model spends up to 75 seconds on compact and publishes as often as standalone smooth clock, with two additional fitted fixes within the paired-v5 bound. At 180 seconds, compact completes 124 fixes, reaches its 165-second cutoff on 26 and fails earlier on eight. Smooth clock supplies 27 fixes, withholds six and times out on one. On the excluded32 specifically, the 180-second model publishes 27/32 versus 22/32 for archived compact and 23/32 for standalone smooth clock.

The one genuinely absent native input never starts either receiver. No historical censor ended earlier than the relevant modeled cutoff on this panel. The retained compact archive timeout at 195 seconds therefore supports a timeout at each shorter primary allowance. The replay code leaves outcomes unresolved when a hypothetical deadline goes past an earlier archival cap. For a canceled stage, it discards that stage's coordinates. The output retains forced coordinates only from a selected solver's measured terminal response.

Conditional RF RMS is reported by selected solver. At 180 seconds the median was 70.85/70.79 Hz for the 124 compact responses and 168.68/145.48 Hz for the 33 smooth responses with RF estimates, in `c=0`/fitted order. The two solver residuals use different observation populations. Position metrics and coverage are scored separately.

The deadlines represent 10%, 30% and 60% of a nominal five-minute capture and begin after acquisition. The model uses historical host worker times measured under different loads. It assumes serial work and adds no new startup, cancellation or packaging overhead beyond the recorded worker intervals. Its timing describes an estimate from the archives, with actual deadline execution addressed in the separate live trial.

```sh
scratch=$(mktemp -d /tmp/deadline-roof.XXXXXX)
.venv/bin/python -B -m tools.pipeline_eval.qualification.deadline_roof_model \
  --out "$scratch/evidence"
.venv/bin/python -B -m tools.pipeline_eval figures --panel screening \
  --variant deadline_roof --evidence "$scratch/evidence" --out "$scratch/charts"
```

[Normalized positions and call receipts](positions.jsonl.gz) · [Chart definitions](figures.json) · [Prediction seal](prediction-lock.json)
