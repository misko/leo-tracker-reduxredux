# Cumulative compact release on saved original GLRT

The cumulative release rule qualified one of six recordings. Its early fix missed the 10% geographic allowance in both coefficient arms against all four original v5 roles. The two recordings with complete original GLRT timing both rejected and saved zero detector CPU in the model. The test gives no basis to add the extra compact fits to the receiver. [Protocol](PROTOCOL.md) · [Input and source lock](source-lock.json) · [Release decisions](release-decisions.json)

## Accuracy and RF fit

Each position worker rebuilt Graph from the visits that had closed by its cutoff. The 210 and 255 s fits shared the capture prefix and the original causal catalogue. The full attempt used the terminal archive. All twelve matched checkpoint attempts returned both coefficient arms. Five of six recordings exceeded both geographic allowances against every original v5 role at the 255 s checkpoint. All five gate rejections exceeded both the displacement and nominal-radius thresholds. DS26-0237 was the one recording within both accuracy allowances at 255 s, and the gate rejected it. [Checkpoint attempts](checkpoint-predictions.jsonl.gz) · [Per-arm scores](scores.csv)

DS29-0519 was the only early release. The 210 and 255 s estimates differed by 143 m with `c = 0` and 146 m with fitted `c`. Its 255 s geographic errors were 0.797 and 0.866 km. All four original v5 roles had errors of 0.248 and 0.319 km on the same recording. Behind a tail barrier, 1,016 valid visits could have been held on this capture. The matched serial model with stored factors already available places the early decision at 376.6 s. This case has no bound original detector timing in the study, so its potential detector CPU savings are unquantified. [Paired timings](timing.csv)

The policy used the actual full result on the other five recordings and published four of those fallbacks. DS26-0162 reached the complete-fit cap, as did the separate full control on DS29-0519. Overall, five policy positions returned against four from the complete-only controls. The median errors among returned policy fixes were 0.633 km with `c = 0` and 0.579 km with fitted `c`. The complete-only medians were 0.601 and 0.547 km on their four returned fixes. [Summary](summary.json)

| Policy arm | Baseline misses at 5% / 10% | Selective-gap misses | Omitted-track-one misses | Omitted-tracks misses |
| --- | ---: | ---: | ---: | ---: |
| `c = 0` | 2 / 2 | 2 / 2 | 3 / 3 | 3 / 3 |
| Fitted `c` | 2 / 2 | 2 / 2 | 3 / 2 | 3 / 2 |

Each table cell uses all six matched recordings, including the timeout. Across the six 255 s pairs, fitting `c` lowered conditional RF RMS on four, with a median change of −0.022 Hz. The corresponding median geographic change was +31 m, and error fell on three. The compact conditional frequency objective rose by a median 2.30 in the same pairs. The two arms used matched observations and search settings. [Paired coefficient ablation](coefficient-ablation.csv)

## Shifted geometry

Both 15 km east shifts failed the face clearance rule at 255 s and withheld early. The constrained 255 s endpoints were 0.376 and 0.271 km from the survey on DS26-0237, and 1.411 and 1.590 km on DS29-0082. Both shifted squares still contained the surveyed position by about 2.70 km. A supplemental test used disjoint 30 km east offers on the same two anchors. The early gate withheld both disjoint cases, but the complete fallback published positions 12.49–12.55 km from the survey in both arms. [Shifted queries](shifted-queries.json) · [Position figures](charts/index.html) · [Disjoint offer results](omitted/README.md)

## Raw timing and compact cost

Both raw-timing anchors rejected the early fix. The archived original-quality GLRT replays processed the complete recordings and reproduced the exact native candidate rows and clock ledgers used here. The last 45 s contained 1,016 valid visits on DS26-0237 and 740 on DS29-0082. A receiver that held those visits until the gate could skip their measured detector cost only after a qualifying decision. The observed anchors instead ran both prefix fits and the actual full fallback. [Capped position stages](position-stages.csv) · [Timing rows](timing.csv)

| Anchor | Measured original detector CPU (s) | Detector CPU after 255 s (s) | Measured speculative compact CPU (s) | Modeled 8-worker fallback delay, eager / held tail (s) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0237 | 2,914.74 | 441.45 | 114.53 | 98.36 / 191.97 |
| DS29-0082 | 3,035.22 | 457.69 | 71.90 | 45.30 / 107.44 |

The eager eight-worker model started every original GLRT visit before either gate completed, by 107.69 s on DS26-0237 and 47.23 s on DS29-0082. The one- and four-worker models still had undispatched raw work when the gates rejected. In those two scenarios the full raw queue took long enough to hide the speculative wall time. Actual compact fits ran once per input under shared host load on CPUs 14–17. The raw worker counts and critical path are simulations driven by the older, directly measured per-visit times. Compact service CPU and stage wall are current measurements. [Stage figure](stage.png) · [Stage PDF](stage.pdf) · [DS26 original raw receipt](../../original-support/prepared-waveform/README.md) · [DS29 original raw receipt](../../antenna-confirmation/capture-whole/README.md)

The largest compact service charged 369.25 MiB and all services reported zero swap. The support diagnostic used at most 0.825 s of measured wall per invocation. On DS29-0519's full control, the supervisor initially could not lock the completed service log. The recovery command authenticated the original terminal timeout and resource receipt without running a new fit. Its separate input preparation timing was unavailable. The timing file flags the lower-bound model that uses zero for that one preparation term. [Supervisor recovery](supervisor-recovery.json) · [Prediction lock](prediction-lock.json)

## Reproduce the study

The receiver and release rule remained fixed while measuring the registered roster. Two initial harness checks fixed audit plumbing before the final source lock. The first preserved the clock anchor before Graph preparation consumed the document. The second captured support for exact gate objects when compact reused an accepted family result. Both kept the same science settings, input roster, and release thresholds. [First audit source lock](preflight-source-lock.json) · [Second audit source lock](preflight2-source-lock.json)

The archive preserves the exact trial, worker, and recovery source bytes used for the sealed outcomes. Its relative-path ledger binds those bytes to the primary and supplemental source locks and the primary recovery receipt. The current repository source includes formatting and import-order fixes. [Source archive](as-measured-sources.tar.gz) · [Source digest ledger](as-measured-sources.json)

To render the sealed measurements into a new figure folder, use the screening chart command. The two chart pages cover the original 25 km offer and the shifted controls for each coefficient arm. The stage figure uses the measured compact stages and the modeled raw schedule. [Figure descriptions](figures.json) · [Screening charts](charts/index.html) · [Score lock](score-lock.json)

```bash
python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/receiver-deadline/sequential-fix \
  --out /var/tmp/sequential-fix-charts
```
