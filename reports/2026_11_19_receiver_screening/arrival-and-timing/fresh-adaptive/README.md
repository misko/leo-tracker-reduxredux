# Fresh waveform adaptive fifth-region admission

Two metadata-selected recordings were frozen before their positions were opened. DS26-0026 has 6,770 scheduled arrivals and DS29-0047 has 6,769. Each ran the same stored IQ and physical release clocks through the unchanged one-active-plus-one-waiting policy. Adaptive chooses five pilot regions when idle, four when one earlier visit is outstanding, and drops an arrival when both slots are occupied. Always-fifth uses five regions for every admitted valid visit. Hardware-invalid arrivals bypass both policies. [Protocol](PROTOCOL.md) · [Preregistered inputs and program identities](preregister.json)

Raw services ran in opposite order on each recording's dedicated host core. DS26 used CPU 18 for adaptive then always-fifth, and DS29 used CPU 19 for always-fifth then adaptive. One complete raw capture and both complete expected detector envelope streams were authenticated before starting each lane. The worker checked each actual emission against the corresponding named branch. The numerical runner independently checked the emitted hashes and exact candidate payload of each reference packet before binding it to the original causal orbit history and offered region. Dropped visits remain absent from the numerical observations. [DS26 raw source](DS26-0026-source-lock.json) · [DS29 raw source](DS29-0047-source-lock.json)

The numerical phase ran separately on CPUs 12 and 13. It included a fresh exact complete four-region stock fit on each recording in addition to the two paced policies. The four original v5 options provide archived geographic references on their capture-era measurements. DS29-0047 uses its independent extended roof authority. These are saved-IQ host services. [Numerical plan](position-plan.json)

## Raw paced results

All **27,078 scheduled arrivals** were accounted for across the four actual replay services. All emitted envelopes matched the named original detector branch, and both policies accounted for the exact same hardware exclusions within each recording. [Complete measured raw clocks and cases](raw-budget.csv)

| Recording | Policy | Order | Hardware-invalid | Emitted four / five | Queue drops | Emission age P50 / P95 (ms) | Raw service CPU (s) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0026 | Adaptive | First | 11 | 3,036 / 3,219 | 504 | 45.4 / 105.4 | 230.55 |
| DS26-0026 | Always-fifth | Second | 11 | 0 / 6,681 | 78 | 41.7 / 70.9 | 251.04 |
| DS29-0047 | Always-fifth | First | 57 | 0 / 6,237 | 475 | 54.4 / 107.0 | 252.10 |
| DS29-0047 | Adaptive | Second | 57 | 1,868 / 4,793 | 51 | 39.5 / 64.9 | 239.76 |

Adaptive emitted fewer visits on DS26 and more on DS29. Across both recordings the drop totals were 555 adaptive and 553 always-fifth. The first run on each recording had the larger drop count even though run order reversed between recordings. P95 host release lag was 6.86 and 3.49 ms in first runs and 1.03 and 0.99 ms in second runs. These single realizations leave a policy timing effect unresolved from host replay order and conditions. Adaptive consumed less raw service CPU in both pairs. [Emission age and queue chart](fresh-arrival.png)

Raw worker wall was 300.97–302.14 s in the 350 s services. Each charged peak reached the 512 MiB limit without OOM or swap. Only 26 native calls across adaptive runs met the 20 ms detector-wall target, and the always-fifth runs had zero. No emitted packet reached the output within 20 ms from its recorded arrival. These are separate metrics from the numerical position services.

## Position accuracy and conditional RF

All six fresh numerical fits published in both calibration arms. Adaptive improved on paced always-fifth on both recordings, by 0.170 / 0.164 km on DS26 and 0.043 / 0.039 km on DS29 at `c = 0` / fitted `c`. The complete unpaced stock fit had lower error than both paced fits on each recording. Its DS26 fitted-calibration result was within 0.4 m of adaptive by absolute error. Every method was at or below 105% and 110% of the original no-repair v5 error in 2/2 recordings in each calibration. The archived v5 methods use capture-era factors. [Scores and exact coverage](scores.csv) · [The four original v5 options](capture-era-v5.csv)

| Recording | Input | Position error (km), `c = 0` / fitted | Conditional RF RMS (Hz), `c = 0` / fitted | Observations / tracks |
| --- | --- | ---: | ---: | ---: |
| DS26-0026 | Complete stock | 0.547 / 0.553 | 84.53 / 84.52 | 4,154 / 113 |
| DS26-0026 | Paced adaptive | 0.560 / 0.553 | 88.49 / 88.47 | 3,995 / 113 |
| DS26-0026 | Paced always-fifth | 0.731 / 0.717 | 86.75 / 86.69 | 4,463 / 124 |
| DS29-0047 | Complete stock | 0.392 / 0.355 | 93.90 / 93.95 | 4,372 / 139 |
| DS29-0047 | Paced adaptive | 0.519 / 0.489 | 92.70 / 92.79 | 4,638 / 148 |
| DS29-0047 | Paced always-fifth | 0.562 / 0.528 | 93.46 / 93.43 | 4,461 / 151 |

Adaptive's DS26 conditional RMS rose compared with always-fifth as its geographic error fell. On DS29 both metrics improved. Each fresh complete-stock solve reproduced its already sealed whole-IQ position and RF values exactly for both calibration arms. [`c = 0` positions](charts/c0/fresh-paced-adaptive.png) · [Fitted `c` positions](charts/fitted_c/fresh-paced-adaptive.png) · [Exact complete-stock parity](stock-parity.csv)

The capped position workers used 74.76–87.78 CPU s and 75.06–96.92 wall s each. The largest numerical cgroup charge was 433.3 MiB. All four paced numerical inputs contain exactly their independently verified emitted visits. The preserved launch sources record a working-directory binding before raw replay and an import-only numerical runner formatting change. The reporting process was restarted after its initial wait was cut short. All six fits retained their original prediction seals. [Numerical resources and checked emission counts](position-resources.csv) · [Position source audit](position-runner-audit.json) · [Prediction seal](prediction-lock.json)
