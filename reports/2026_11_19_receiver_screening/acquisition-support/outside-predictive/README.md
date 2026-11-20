# Reciprocal held Doppler for interior and exterior ensembles

The held evidence correctly identified **4/4 synthetic omissions** and **3/4 synthetic containing offers**, with one ambiguous containing offer. On the measured roof archive it correctly identified only **1/4 omissions** and classified the other three as inside, despite learning the orbit and calibration on time blocks disjoint from their scoring data. All three incorrect inside classifications were known false smooth publications. They remained published. The added rule changed **0/16 publication decisions**. [Frozen protocol](PROTOCOL.md) · [Per-offer scores](scores.csv)

## Publication and geographic evidence

The two synthetic recordings were drawn at different sites and at 1.75 and 6.0 h after the authenticated TLE collection. Four offers share each recording. The separately diagnosed real cohort uses eight unchanged native-factor offers from two roof recordings. Each row has four offers over two captures. Both calibration arms made the same final decisions. [Sealed geometry and source](evaluator.json) · [Full outcome distributions](summary.json)

| Cohort and true region | Evidence says inside | Evidence says outside | Ambiguous | Ordinary published | Published with veto |
|---|---:|---:|---:|---:|---:|
| Fresh synthetic containing | 3/4 | 0/4 | 1/4 | 0/4 | 0/4 |
| Fresh synthetic omitted | 0/4 | 4/4 | 0/4 | 0/4 | 0/4 |
| Diagnosed roof containing | 4/4 | 0/4 | 0/4 | 2/4 | 2/4 |
| Diagnosed roof omitted | 3/4 | 1/4 | 0/4 | 3/4 | 3/4 |

Both near and both far synthetic omissions favored the exterior in every calibration and split. Their smallest positive score advantage across those comparisons was 11.50 natural-log units. On the one ambiguous synthetic near-inside offer, the `c = 0` comparisons favored the interior by 15.61 and 14.07. Fitted `c` favored the exterior by 3.74 and 8.86. The ordinary receiver withheld all eight synthetic offers, six on geometry and two on held-track support. The two centered forced fits used for evidence were close to truth, with the corresponding split-fit positions and comparison scores in the CSV. [Synthetic figures](fresh-synthetic/figures.json)

| Diagnosed omitted offer | Held evidence | Published errors, `c = 0` / fitted `c` |
|---|---|---:|
| DS26-0102, near | Inside | 4.548 / 4.678 km |
| DS26-0102, 6 km outside | Outside | Withheld by the original gate |
| DS26-0070, near | Inside | 14.549 / 14.964 km |
| DS26-0070, 6 km outside | Inside | 10.892 / 11.097 km |

The three incorrect roof classifications favored the interior by 178.70–431.65 log-score units across their four comparisons. The two split-trained locations for the DS26-0102 near omission were already about 9–10 km west of the tile center and inside the wrong square. On the DS26-0070 near omission the two trained locations were also inside, at approximately −8.8 and −3.4 km in east position with `c = 0`. The independent blocks repeated the geographically wrong training model's preference. The two genuine published roof fixes retained their original errors and conditional fit. [Measured roof figures](archived-roof/figures.json) · [Exact per-arm positions](native_outside_predictive.jsonl.gz)

## Held frequency and receiver boundary

On the second synthetic site's near omission, the two `c = 0` splits' descriptive best-node interior RMS values were 1,214 and 1,032 Hz. The exterior values were 183 and 195 Hz. At the measured DS26-0102 near false fix, the interior values were 14.14 and 16.51 kHz versus 14.54 and 16.92 kHz outside. These compare the same wrapped held measurements. The winner-node RMS describes each region's most predictive sampled location. Individual large residuals receive limited weight in the log score through its uniform contamination term. The synthetic split forecasts used at least 12 assigned orbits per comparison and the roof forecasts at least 26. The method's strong wrong-site preferences on measured data make the synthetic separation insufficient evidence for deployment. [Conditional RF and held scores](scores.csv)

Each numerical request starts with complete stored native factors and a causal TLE. The ordinary receiver uses its original full Graph. The verifier independently rebuilds a training Graph on even 6 s blocks and predicts the untouched odd blocks, then reverses the roles. The fitted orbit identities, phases, calibration coefficient, lane terms and smooth clock stay fixed across 48 interior and 48 exterior nodes in each comparison. Held peaks are nominated by a uniquely assigned training track's lane and time span. Score contributions are averaged per orbit and 6 s block before the normalized spatial mixture. The quoted log advantages are predictive scores conditional on those training assignments and a finite equal-budget geometry set. The older exterior test evaluates its single selected alternative after training-dependent nuisance fits. This test uses an integrated alternative and one frozen training calibration for both regions in each split. [Scientific source lock](source-lock.json) · [Earlier exterior evidence](../../recovery/exterior-evidence/README.md)

All 16 jobs completed without failures or timeouts in **78.12 s** on CPUs 16 and 17. Full worker median / P95 / maximum wall time was **9.14 / 10.75 / 10.77 s**, with CPU time of **8.86 / 10.31 / 10.31 s**. The extra reciprocal Graphs, training and held forecasts used **4.26 / 4.74 / 4.76 s** wall and **4.24 / 4.64 / 4.73 s** CPU. Peak RSS was **206,696 KiB** and peak address space was **446,520 KiB** under the original 512 MiB cap. All eight ordinary archive results and Graphs exactly reproduced the previous inputs and outputs. The two complementary Graph digests stayed fixed across all four offers of each capture. [Prediction seal](prediction-lock.json) · [Both-arm plots](charts/manifest.json)

To reproduce, use a fresh scratch directory and an authenticated native-lean deployed-source bundle. A fresh execution draws a new seed; the recorded seed is available in the sealed evaluator for regenerating this simulator cohort. [Exact offered queries](roster.json)

```sh
predictive_work=$(mktemp -d /tmp/leo-outside-predictive.XXXXXX)
timeout --kill-after=2s 720s taskset -c 16,17 .venv/bin/python \
  -m tools.pipeline_eval.qualification.outside_predictive_trial \
  --work "$predictive_work/run" --bundle /path/to/deployed-source \
  --output "$predictive_work/report"
.venv/bin/python -m tools.pipeline_eval.qualification.outside_predictive_results \
  --work "$predictive_work/run" --output "$predictive_work/report"
```
