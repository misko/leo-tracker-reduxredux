# DS29-0247 full recorded-IQ replay under 512 MiB

The release is available as `--profile phase-release` in the standalone installer. A fresh installation replayed the same raw recording in 142.25 s with 194.59 CPU seconds. Both native binaries, every detector candidate, and every scientific position, RF and solver field matched the primary repaired run. This was a packaging check on the already scored recording. It contributes one physical recording across both runs. [Public installation receipt](installed-profile.json) · [Installation and replay commands](../../../../tools/pipeline_eval/README.md)

Releasing constrained-fit buffers let the public narrow receiver finish and publish both calibration arms on DS29-0247. The original narrow receiver hit the cgroup memory limit after raw replay and returned no positions. Both runs visit all 6,767 eligible dual-receiver windows and use the same detector and native factors. The repaired receiver returned **0.711 km** error with `c = 0` and **0.980 km** with fitted `c`. [Position chart, c = 0](charts/c0/whole-pressure.png) · [Position chart, fitted c](charts/fitted_c/whole-pressure.png) · [Scores](scores.csv)

| Full recorded-IQ replay | Terminal result | Wall time | CPU time | Raw replay | Position | Charged peak |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Original narrow | Kernel OOM kill | 144.90 s to failure | 201.58 s to failure | 67.62 s | Censored | 512 MiB |
| Repaired narrow | Published both arms | 158.15 s | 215.36 s | 66.61 s | 90.72 s | 512 MiB |
| Original wide, different detector | Published both arms | 136.20 s | 185.35 s | 75.45 s | 59.90 s | 512 MiB |

The two narrow services used CPU 0/1, 512 MiB, zero swap and a 360 s deadline. The repaired run had zero OOM events and zero swap. The suite's whole-service peak includes the raw replay's file cache. Both narrow trials had already reached the charged peak when raw replay finished, so the prediction that the measured whole-service peak would fall below the cap did not hold. The original narrow service timed only a partial position stage. These are single recorded trials on a shared x86 host, and they establish recovery at the cap and leave the same-detector speed comparison unresolved. [Resource receipts](resources.json) · [Public service log](repair-service.log)

The input used 6,775 recorded visits, with eight excluded by capture validation, 13,534 receiver probes and 10.84 GB of decoded CI16. Native archive SHA-256 `6ea607c55fae631c3e525a12942085495231d4a2d056d4492ab5b7a50a62fb59` matches the original narrow replay byte for byte and passes normalization against the authenticated ordinary archive. Waveform authority, clock, exclusions and probe support match the frozen controls. The repaired position and Doppler RMS also match the independent factor-only run exactly for each arm. [Native archive](native.json.gz) · [Replay source lock](replay-source-lock.json) · [Prediction seal](prediction-lock.json)

| Receiver | Error with `c = 0` | Error with fitted `c` | Doppler RMS with `c = 0` | Doppler RMS with fitted `c` |
| --- | ---: | ---: | ---: | ---: |
| Repaired narrow | 0.711 km | 0.980 km | 98.280 Hz | 98.324 Hz |
| Original wide | 1.326 km | 1.338 km | 65.388 Hz | 65.363 Hz |
| Original v5, no repair | 1.320 km | 1.458 km | 60.751 Hz | 60.633 Hz |

The repaired narrow passed both the 5% and 10% error criteria against original v5 on this reserve recording. All four original v5 options agree on DS29-0247. With the repaired narrow receiver, fitting `c` lowered the conditional frequency score from 34,763.866 to 34,761.690 while Doppler RMS rose by 0.045 Hz and position error rose by 0.269 km. The wide detector changed the factors, and both position error and Doppler RMS are reported independently. [Scores for both arms and every reference](scores.csv)

The first staged package omitted a manifest-bound compiler source. Its replay was stopped during raw processing before it produced a native archive or ran inference. The corrected package includes both original compiler sources and preserves the repaired mathematical source and original libraries. The interrupted launch is retained separately from the scientific denominator. [Transport stop receipt](transport-stop.json) · [Protocol](PROTOCOL.md)
