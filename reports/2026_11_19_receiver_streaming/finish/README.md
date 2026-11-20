# Compact v5 numerical finish

The compact finish reproduced the final v5 coordinates, Doppler RMS and RF objective exactly in both calibration arms on the three matched recordings. A fourth replay exercised conditional residual addition and matched the authenticated v5 endpoints and RF objective in both arms. The largest prior cavity-cutoff loss, DS26-0066, fell from 2.389 to 1.244 km with `c = 0` and from 2.370 to 1.218 km with fitted `c`. [Protocol](PROTOCOL.md) · [Paired comparison](comparison.json) · [Addition extension](addition-extension.json)

## Numerical boundary

The frozen baseline request limits ordered recovery to zero targets and disables direct timing-gap recovery. Predictive recovery therefore creates no attempts, numerical replay has no annotation to reuse, and gap recovery receives no eligible parent. The compact adapter carries the cavity winner and the original published observation owners forward, keeping the frozen objective replay and native ownership checks. It executes the same residual target ranking, causal catalogue screen and paired conditional fit, followed by the same RF influence trigger, shared-receiver admission guard, and paired final selection. It collects the final phase history only if the admission path calls for it. The worker loads stored GLRT detections and bound TLEs. Reference coordinates and historical outcomes enter only the independent scoring code. [Worker](../../../tools/pipeline_eval/variants/compact_finish.py)

The archived audit found twelve DS26 recordings where continuing from the cavity moved the paired positions by more than one metre. Eleven adopted one residual family and retained that addition through final reassociation. DS26-0066 rejected its conditional addition and adopted the final reassociation `62025_to_68047`. The two smoke recordings adopted neither. Both live adoption routes must therefore remain available, even if a tested recording returned its cavity positions. [Twelve archived decisions and their digests](decision-audit.json)

## Geographic and RF results

Each cell with a pair gives `c = 0` followed by fitted `c`. Latitude and longitude are in degrees. Both are reproduced to the stored numeric precision in the two independent finish executions. Geographic errors use the evaluation receiver location after inference. The RMS and objective describe the selected RF fit. An objective from one calibration model includes that model's priors and likelihood.

| Recording | Latitude and longitude, `c = 0` | Latitude and longitude, fitted `c` | Geographic error (km) | Conditional RMS (Hz) | RF objective |
|---|---|---|---:|---:|---:|
| DS26-0066 | 37.85970769, −122.49009927 | 37.85957963, −122.48960530 | 1.244 / 1.218 | 69.875 / 69.942 | 26229.331 / 26239.102 |
| DS26-0036 | 37.85305483, −122.49940304 | 37.85210007, −122.49896065 | 1.278 / 1.208 | 74.761 / 74.682 | 25232.146 / 25232.286 |
| DS29-0082 | 37.84549611, −122.48113274 | 37.84967145, −122.47991582 | 0.567 / 0.517 | 97.004 / 96.684 | 6337.718 / 6342.809 |
| DS26-0002 | 37.85481994, −122.48778563 | 37.85501420, −122.48823948 | 0.665 / 0.697 | — / — | 24156.758 / 24165.931 |

On DS26-0066, fitting `c` gave a 26 m smaller geographic error and a 0.067 Hz higher conditional RMS. On DS26-0002, fitting `c` gave a 32 m larger geographic error. The frozen conditional-addition row records an RF objective and has no aggregate conditional RMS field. The full publication archive separately reports its rendering-stage residual RMS. [Scored endpoints](comparison.json) · [Conditional-addition comparison](addition-extension.json)

## One pinned host CPU

The timing series ran the original full numerical worker, the first compact finish, and its cavity-only control once per recording. Each series used one CPU throughout. Each worker starts with authenticated native detections and ends with both positions. Times include worker startup, any projector compilation, and in-process scientific verification. CPU time also includes the small supervising process that launches the worker and receives its result.

| Recording | CPU | Full v5 wall / CPU (s) | Compact finish wall / CPU (s) | Compact cavity wall / CPU (s) | Full ÷ finish wall / CPU |
|---|---:|---:|---:|---:|---:|
| DS26-0066 | 20 | 373.32 / 362.50 | 283.90 / 277.29 | 161.81 / 153.96 | 1.31× / 1.31× |
| DS26-0036 | 21 | 316.92 / 249.14 | 148.37 / 144.44 | 105.00 / 103.38 | 2.14× / 1.72× |
| DS29-0082 | 22 | 131.81 / 129.82 | 230.79 / 143.07 | 58.35 / 57.46 | 0.57× / 0.91× |

The third compact run spent 99.22 seconds preparing native inputs, compared with 19.77 seconds for its full control. Shared-host and input preparation variability makes the three recording times unsuitable for a population speedup claim. The compact finish recovered the stress fix at the cost of 123.33 additional CPU seconds over the cavity-only worker. Residual screening and reassociation admission alone took 57.32 seconds wall in that finish. The two adoption routes preserve substantial numerical work even after removing the zero-target stages. [Timing receipts](predictions.jsonl)

The adapter confirmations took 253.80 / 251.36 seconds wall / CPU on DS26-0066, 174.29 / 168.97 on DS26-0036, 129.16 / 125.30 on DS29-0082, and 197.98 / 188.98 on the separately selected DS26-0002 extension. Each matched the respective first compact result exactly. The paired timing series above used its own contemporaneous full and cavity controls. [Confirmation receipts](adapter/)

## Reproduce

```bash
.venv/bin/python -m tools.pipeline_eval.qualification.compact_finish_eval --out /tmp/compact-finish
.venv/bin/python -m tools.pipeline_eval.qualification.compact_finish_eval --addition-extension --out /tmp/compact-finish
.venv/bin/python -m tools.pipeline_eval.qualification.compact_finish_eval --score-only --out /tmp/compact-finish
```

The historical timing receipts retain the first implementation hash. The delivered adapter uses the same finish computation and leaves the source-bound cavity and projector controls byte-identical. Its fresh confirmations use the original pins and check coordinates, frequency metrics, associated observation counts, and both adoption decisions. The adapter digests also reflect a whitespace-only import adjustment and a final output-directory check before kernel compilation. The independent checks cover these four roof recordings and their original region, including one accepted example of each adoption route. [Final adapter results](compact_finish.jsonl) · [Confirmation receipts](adapter/) · [Source versions](source-versions.json)
