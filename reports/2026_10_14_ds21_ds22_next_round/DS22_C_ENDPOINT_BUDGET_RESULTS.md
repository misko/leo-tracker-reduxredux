# DS22-105/107: endpoint continuation repairs availability, not localization

The separately frozen four-call experiment recovered strict accepted C estimates on both cases, while preserving the original unavailable results in the cohort. Neither recovered estimate meets the localization target. This is an added optimization-budget experiment, not evidence that past CPU contention caused the original failures.

For each case, the original failed C-all endpoint with minimum training objective was frozen: start 5 on 105 and start 0 on 107. Each endpoint independently initialized a fresh 20-second fit and a fresh 40-second fit. Both arms retained 600 optimizer iterations, the same model, priors, original 25 km disk, fitted c, and strict independent KKT acceptance. The 40-second arm did not start from the 20-second result. Both cases passed exact saved-objective replay, physical feasibility, and a maximum 1e-12 initializer-adjustment gate before any fit began. No failed original fallback was eligible.

| Case | Fresh cap | Evaluations | Fitter wall seconds | Process CPU seconds | Accepted | KKT | Configured distance (km) |
|---|---:|---:|---:|---:|---|---:|---:|
| 105 | 20 s | 290 | 20.103854 | 20.100132 | No | Original strict rejection retained | unavailable |
| 105 | 40 s | 405 | 23.050409 | 23.037669 | Yes | 0.000334017 | 220.157833 |
| 107 | 20 s | 249 | 9.007291 | 9.007020 | Yes | 0.000046281 | 2.937323 |
| 107 | 40 s | 249 | 8.036668 | 8.036312 | Yes | 0.000046281 | 2.937323 |

The accepted 105 objective is 41521.828953 (NLL 40871.180263), versus its new rejected 20-second endpoint objective 41631.396913. Both 107 arms return the identical objective 31805.805427 and endpoint. Original 107 half estimates are 2.491342/0.965570 km, both better than the recovered full estimate. Original 105 half estimates are also hundreds of kilometers away. All distances are against the configured station, unconfirmed for DS22.

Original 105 full starts used only 97–227 evaluations before their 20.11–20.25 second deadlines, with KKT residuals 1792–4817. Original 107 used 144–329 evaluations at 20.08–20.14 seconds, KKT 20.75–9602. Earlier accepted 081 calls used 242–499 evaluations in 4.69–8.78 seconds; accepted 083 calls used 276–337 in 5.34–6.69 seconds. Those are different workloads: 105 has 3071 windows/60 physical parameters, 107 2826/45, 081 2204/33, and 083 2021/38. Historical per-fit process CPU time was not recorded, so these comparisons cannot separate workload, core placement, memory pressure, and scheduling effects.

The host reports 24 physical cores, one thread per core, Intel Core Ultra 9 285K. New calls retained unrestricted affinity 0–23 and single-thread BLAS. Their measured CPU time nearly equals wall time, showing little descheduling during these particular fitter invocations. That does not establish equal core speed or memory throughput, nor retrospectively diagnose original runs.

Each case unit was capped at 120 seconds internally and TERM/KILL 135/140 seconds; 105 completed in 89.761 seconds and 107 in 47.413 seconds. Added scientific cost is four fresh optimizer calls, with two nominal 20-second and two nominal 40-second caps. The 600 limit is optimizer iterations, not total objective evaluations. No automatic continuation follows this experiment.

Sources: control `0c7f8b051`, evaluator `c3c1eae37`. Namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c-budget-control-v1`; comparison in adjacent `ds22-c-budget-comparison-v1/report.json`. Both two-call unit seals were verified before the reference join. Original matrices and the cohort's six unavailable C-all outcomes remain unchanged. No accuracy-target or model-promotion claim follows.
