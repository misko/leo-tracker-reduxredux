# Physical winner discordance on exact capture support

This replay starts from the availability experiment's exact capture-positive hybrid. It changes winner measurements only on the subset of originally jointly positive probes whose reported winners differ by more than the strict wrapped epoch or CFO tolerance. Every other probe retains its exact hybrid values. Capture-era winners determine the intervention, so these are oracle treatments on two recordings from the same roof.

| Recording | Joint positives | Same strict winner family | Matching gated wide alternative | Matching ungated only | Near epoch, wrong CFO | No nearby wide epoch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS29-0082 | 1,634 | 1,538 | 34 | 0 | 0 | 62 |
| DS26-0237 | 3,417 | 3,326 | 37 | 0 | 0 | 54 |

The strict rule allows 0.2 microseconds in epoch modulo the 750 Hz frame and 1 kHz in CFO modulo the fractional alias period. The census uses actual winning candidates from each detector, then tests all exported wide candidates against the capture winner. A gated wide alternative is a ranking opportunity in the stored factors. Every donor-required row in this cohort lacks a nearby wide epoch even among ungated candidates. The factor exports give no earlier-stage record of where that epoch was lost. [Frozen protocol](PROTOCOL.md) · [Exact census](census.json) · [Per-probe alternative and donor selections](selections.jsonl.gz)

Three interventions select an already exported wide alternative, copy the capture winner only where an admitted alternative is absent, or copy the capture winner at every physically discordant probe. Rank bookkeeping in a donor move retains the existing wide candidate slot. Its epoch, CFO, flags and scores are the donor's original measurement. The exact stock capture comparator also uses its own same-family winners. All conditions retain the original positive roster and genuine causal TLE history. [Prospective plan](plan.json) · [Baseline availability cross](../support-cross/README.md)

## Location and frequency results

On DS29-0082, selecting all 34 available wide alternatives recovered 0.335 km at `c = 0` and 0.097 km with fitted `c`. Replacing the 62 missing-epoch winners alone increased errors by 0.170 and 0.317 km despite reducing conditional RF RMS. The largest improvement came from taking the capture winner on all 96 discordant rows. That closed **91%** of the exact-support gap at `c = 0` and **45%** with fitted `c`, leaving gaps of 0.113 and 0.748 km to stock capture. The combined treatment also substitutes capture measurements on the 34 rows that already have a gated wide alternative. The three interventions leave its gain unresolved between those measurement substitutions and joint changes across the two probe classes.

On DS26-0237, each treatment improved both position arms. Copying all 91 discordant winners gave the closest fit, with errors of 0.250 and 0.149 km. Its conditional RF residuals exceeded those of the exact capture fit. Across the two recordings, the gated wide alternative helped in both calibration arms, with the larger recovery requiring capture measurements on both discordance classes. [Paired positions, RF and differences from the hybrid](scores.csv)

Values below are `c = 0` / fitted `c`. The exact support and capture comparators are sealed results from the preceding availability cross. Original stock wide uses its original distinct support.

| Recording | Condition | Error (km) | Conditional RF RMS (Hz) | Prepared tracks |
| --- | --- | ---: | ---: | ---: |
| DS29-0082 | Stock wide | 2.489 / 2.346 | 84.42 / 84.25 | 71 |
| DS29-0082 | Exact support hybrid | 1.811 / 1.884 | 86.52 / 86.52 | 60 |
| DS29-0082 | Gated wide alternative | 1.476 / 1.787 | 82.17 / 81.97 | 60 |
| DS29-0082 | Donor required | 1.981 / 2.201 | 81.67 / 81.47 | 64 |
| DS29-0082 | All discordant to capture | 0.681 / 1.264 | 81.58 / 81.40 | 62 |
| DS29-0082 | Stock capture | 0.568 / 0.516 | 97.00 / 96.68 | 61 |
| DS26-0237 | Stock wide | 0.382 / 0.323 | 92.54 / 92.43 | 110 |
| DS26-0237 | Exact support hybrid | 0.430 / 0.339 | 89.07 / 88.99 | 104 |
| DS26-0237 | Gated wide alternative | 0.386 / 0.311 | 87.05 / 87.00 | 101 |
| DS26-0237 | Donor required | 0.328 / 0.221 | 87.57 / 87.50 | 104 |
| DS26-0237 | All discordant to capture | 0.250 / 0.149 | 89.16 / 89.04 | 105 |
| DS26-0237 | Stock capture | 0.353 / 0.262 | 80.67 / 80.61 | 103 |

## Execution and figures

All six new services published both arms. Staged factor and request hashes match the prediction seal. The post-seal audit checked every candidate against the exact hybrid or intended donor, including preserved same-family winners and negative probes. All services ran under 512 MiB with no swap and a 210 s service deadline. CPU was 24.77–45.83 s per service and worker wall time was 24.95–50.02 s, with 403.6 MiB peak cgroup charge and zero OOMs. These timings start at stored GLRT. [Treatment audit](treatment-audit.json) · [Resource measurements](resources.csv) · [Graph support](graph-support.csv) · [Sealed evidence](prediction-lock.json)

- Gated wide alternative. [`c = 0`](charts/c0/shared-winner-wide-alternative.png) · [Fitted `c`](charts/fitted_c/shared-winner-wide-alternative.png)
- Donor required. [`c = 0`](charts/c0/shared-winner-donor-required.png) · [Fitted `c`](charts/fitted_c/shared-winner-donor-required.png)
- All discordant winners. [`c = 0`](charts/c0/shared-winner-all-discordant.png) · [Fitted `c`](charts/fitted_c/shared-winner-all-discordant.png)
