# Partner on hits plus a quarter of primary misses

The frozen policy keeps the complete fixed-four partner packet after every strict primary hit. It also keeps one of every four primary misses in each recorded RF and physical-primary-lane stream. A stable hash gives each stream its starting phase. Hits and invalid visits leave the miss counters unchanged. The quarter fraction targets about 75% of full stereo calls when one third of primaries hit. The policy uses the primary gate and recorded visit sequence alone. [Protocol](PROTOCOL.md) · [Prospective policy lock](policy-lock.json)

The earlier fourteen form a post-hoc robustness cohort, because their partner-on-hit positions motivated this experiment. DS26-0066 and DS29-0085 form the separate prospective cohort. Their identities, source seals and unchanged decision code were frozen before their geographic results were opened. On both prospective recordings, the earlier direct saved-waveform on-hit candidate reproduced exactly when projected from the same complete stock body. These two recordings also received fresh primary-only numerical comparators. [Numerical plan](plan.json) · [Packet audit](packet-audit.json)

The trial uses the unchanged installed phase-release compact receiver and the original truth-free requests, causal catalogues and offered tiles. Each saved-factor service uses one numerical thread, pins its assigned CPU among 14, 15, 18 and 19, and runs with 512 MiB, zero swap and a 210 s cap. The measured boundary starts from authenticated detector factors and produces both calibration arms. The call counts describe the schedule. The original v5 geographic reference archive is independently sealed. [Resource measurements](resources.csv) · [Call and observation census](support.csv) · [Capture-era v5 roles](capture-era-v5.csv)

The per-recording tables compare the full, primary-only, on-hit and quarter-miss positions. Conditional RF RMS and the frequency objective are measured separately from horizontal error. The 5% and 10% allowances use same-recording original v5 and fixed-four controls. [Paired effects](effects.csv) · [Full scientific scores](scores.csv) · [Position charts](charts/README.md)

## Prospective recordings

Both prospective quarter-miss positions improved over on-hit in both arms. Both full-stock fits had lower error still. Each table entry gives `c = 0` / fitted `c` in km.

| Recording | Alternating primary | Partner on hit | Partner on hit plus quarter misses | Both stock lanes |
| --- | ---: | ---: | ---: | ---: |
| DS26-0066 | 2.701 / 2.714 | 2.380 / 2.371 | 2.250 / 2.238 | 2.201 / 2.191 |
| DS29-0085 | 2.329 / 2.200 | 1.753 / 1.628 | 1.611 / 1.384 | 1.217 / 1.093 |

The fitted-c conditional RF changes from on-hit to quarter-miss were +3.420 Hz on DS26-0066 and −0.012 Hz on DS29-0085. The two new recordings schedule 18,038 lane calls, 72.8% of the full stereo count, and regain 407 gated observations on 2,248 audited misses. The original v5 references were published after the prospective policy lock. [Per-recording scores](scores.csv) · [Support counts](support.csv)

## Post-hoc fourteen

Adding quarter-miss observations to on-hit improved five of fourteen `c = 0` positions and six of fourteen fitted positions. The median paired error increased by 35 m and 17 m. Median paired conditional RF RMS fell by 0.665 and 0.668 Hz. Relative to primary-only, quarter-miss improved ten of fourteen in each arm, with median paired error reductions of 275 m and 247 m. Each table entry gives `c = 0` / fitted `c`. [Paired effect summary](effects-summary.csv)

| Recorded support | Median error, km | P95 error, km | Within 10% of original v5 | Scheduled calls | Gated observations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Alternating primary | 0.748 / 0.687 | 1.760 / 1.758 | 7 / 7 | 94,142 | 29,963 |
| Partner on hit | 0.742 / 0.688 | 2.424 / 2.405 | 11 / 10 | 124,105 | 48,931 |
| Partner on hit plus quarter misses | 0.643 / 0.648 | 2.398 / 2.379 | 9 / 9 | 140,149 | 51,670 |
| Both stock lanes | 0.774 / 0.765 | 1.517 / 1.375 | 12 / 11 | 188,284 | 59,859 |

The additional 16,044 calls, for 74.4% of full stereo, recovered 2,739 gated observations. DS26-0168 gained 179 of them, but its fitted error stayed near 4.155 km. With both stock lanes it was 0.796 km. The quarter-miss results retain the upper-tail failure that motivated the test. [Support census](support.csv) · [Per-case effects](effects.csv)

All eighteen numerical services returned both calibration arms, including sixteen quarter-miss fits and the two prospective primary-only comparators. The post-hoc quarter-miss jobs took 61.0–182.6 s from stored factors, with median wall and CPU times of 83.9 and 73.7 s. Peak memory was 407.2 MiB with zero swap. The two prospective quarter-miss jobs took 40.5 and 57.2 s at the same numerical boundary. [Terminal resources](resources.csv)

## Reproduction

The report keeps the fixed policy and exact input source bindings in `policy-lock.json`. From a checkout with those same sources and no existing numerical plan, run `python -m tools.pipeline_eval.qualification.quarter_miss_trial /path/to/new/local/work`. After the prediction lock is sealed, run `python -m tools.pipeline_eval.qualification.quarter_miss_results /path/to/work --plot /path/to/plots`. [Terminal prediction lock](prediction-lock.json)
