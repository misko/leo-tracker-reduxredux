# Stationary localization across independent sessions

The three early and three later roof recordings independently selected the same 5 km grid cell. That cell was 7.942 km from the survey and lost to a separated rival on the later held blocks. Pooling all six recordings added no geographic improvement over either three-session group. All three offered squares were withheld. [Held spatial support](stationary-support.png) · [Both-arm position charts](charts/index.html) · [Per-method scores](scores.csv)

## Measured roof

DS26-0002, DS26-0030 and DS26-0058 form the early group. DS29-0082, DS29-0127 and DS29-0174 form the later group. Timestamp and authenticated input availability selected both groups. Together they cover 30 minutes of acquisition across 11.73 elapsed days at one surveyed roof. The model treats the site as stationary across that span and fits each acquisition's receiver clocks independently. [Frozen protocol](PROTOCOL.md) · [Truth-free input roster](blind-plan.json) · [Position decision seal](decision-lock.json)

| Supplied square | Six-session forced error | Offer center error | Held spatial lead | Early choice on later held blocks | Publications |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original containing | 7.942 km | 8.193 km | +0.000296 | −0.002378 | 0/1 |
| Near missing | 7.942 km | 16.095 km | +0.000296 | +0.002055 | 0/1 |
| Far missing | 38.439 km | 45.243 km | −0.032845 | −0.034974 | 0/1 |

Spatial lead is mean held log likelihood at the chosen cell minus the best score at a cell at least 10 km away. All methods evaluate the same union of three 25 km offers and three exterior points. The near-missing offer and original offer share the winning grid cell 10 km east of the original center. The far-missing square's best conditional point lost to a cell outside it. Its forced error reduction versus its center leaves a 38.439 km error. [Sealed offered geometry](queries.json) · [Survey-independent score vectors](session-profiles.jsonl.gz)

The first recording alone selected a cell 4.978 km from the survey. Across all six single-recording fits, forced errors spanned 4.978–12.467 km. Every chronological prefix from two through six sessions picked the same 7.942 km cell. Its held score was +0.005370 log units over the offered center and +0.116478 over the same cell with a 73 s cyclic time shift. Its pooled geographic lead was +0.000296 against the preregistered +0.040 publication requirement. The time-shuffle fit independently selected a cell 22.311 km from the survey. The matched original no-repair v5 positions had 0.567–1.137 km errors with `c = 0` and 0.517–1.115 km with fitted `c`. They used richer RF inference. [Session and prefix rows](scores.csv) · [Standard controls chart](charts/c0/stationary-controls.png)

## Physics and measured work

The likelihood starts at authenticated native GLRT alternatives and each acquisition's causal TLE snapshot. Same-receiver, same-RF snapshots contribute anonymous wrapped frequency differences, and all retained alternatives and visible orbit predictions enter a normalized signal/clutter mixture. Each receiver has a separately marginalized drift in every acquisition. Constant LO and RF-dependent `c` cancel in the difference. The two chart arms are identical for this observable. Each acquisition's clock posterior is estimated from its training clock factors and applied to its own held 20 s blocks. The forward comparison takes the early group's fixed position to the later group, where only the clock nuisance uses those later training blocks. Orbit candidates are marginalized independently in every session.

All six workers completed on CPUs 20–21 under the 150 s and 512 MiB address-space caps. Their 2,412 eligible lane slices covered 445 four-second epochs, 149 of them held. The total process CPU time was 243.54 s and the median was 38.11 s per session. Worker wall times were 16.87–104.37 s and peak process RSS was 245.90 MiB. The workers ran 371.35 million paired orbital-rate evaluations, excluding repeated density calculations over the clock grid. This timing begins at the archived GLRT output boundary. [Runtime summary](summary.json) · [Worker profiles and cap receipts](session-profiles.jsonl.gz)

## Independent simulated sites

Two freshly generated sites each used independent transmitters, oscillator states, sample clocks and GLRT alternatives in two five-minute captures starting twelve hours apart. They supplied a separate check on the site accumulation mechanism with simulated observations. The omitted-offer controls were conditioned on the registered hidden geometry. [Simulation protocol](SIMULATION.md) · [Blind plan](simulation/plan.json) · [Sealed predictions](simulation/prediction-lock.json) · [Released labels](simulation/released-labels.json)

| Containing offer | Two-session forced error | Center error | Early choice on later held blocks | Pooled held spatial / timing lead |
| --- | ---: | ---: | ---: | ---: |
| Western Americas site | 5.901 km | 5.310 km | −0.003653 | +0.002265 / +0.177660 |
| Australia site | 7.546 km | 5.566 km | −0.006114 | −0.001858 / +0.285792 |

Both containing offers and both offers in each missing condition were withheld. The near misses shared the containing offer's preferred cells and the far misses had forced errors of 35.981 and 36.251 km. The four workers completed in 21.30–37.69 s wall apiece, used 61.76 CPU-seconds in total and peaked at 191.99 MiB process RSS. [Simulated position charts](simulation/charts/index.html) · [Per-site scores](simulation/scores.csv) · [Per-capture resources](simulation/profiles.jsonl.gz) · [Exact generated inputs](simulation/as-run-inputs.tar.gz)

## Reproduce

Choose an unused local output and copy the frozen protocol into it. Stage and run one worker per session, then seal location decisions before opening survey labels or original v5 references.

```bash
trial=tools.pipeline_eval.qualification.multi_session_trial
score=tools.pipeline_eval.qualification.multi_session_results
python -m "$trial" stage "$WORK" --report "$REPORT"
python -m "$trial" run "$WORK" --report "$REPORT"
python -m "$score" decide --report "$REPORT"
python -m "$score" score --report "$REPORT" --render
python -m tools.pipeline_eval.qualification.multi_session_stage --report "$REPORT"
```

The stage exporter reads the sealed scores and the existing support image and PDF. It emits the 45 plotted points with their acquisition number, offer and held group for the generic benchmark pack. [Plotted input CSV](stationary-support.csv) · [Stage descriptor](stage-figure.json) · [Stage seal](stage-figure-lock.json)
