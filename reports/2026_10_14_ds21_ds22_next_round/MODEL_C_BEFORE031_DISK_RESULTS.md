# Before031 independently replicates a geographic search restriction

The separate **before031** matched control improved configured-reference error **26.287028736 → 10.221272805 km** after recentering a 25 km disk on the same original all-band winner. Both returned endpoints are independently stationary and replay objective/NLL/KKT exactly. This is a second case supporting the boundary mechanism; it remains far from the sub-km/0.5 km goal. Its all-band result beats the unchanged original low/high errors 38.533578502/36.274699614 km. The before branch is reported separately from the frozen ten-case after cohort and does not replace baseline histogram inputs.

Here the geometry restriction is stronger than C003's winning-path restriction. The new endpoint lies outside **every** original all-band proposal disk: distances from their actual centers are 105.602440537, 40.540080462, 51.301971469, 45.485305607, 68.491934201 and 48.645271234 km, all greater than 25 km. The winning original center was `[-43.75,-106.25]`; actual cold-0 was `[-25,-175]`. No assumed generic cold center or reference seed was substituted. Thus the improved state was excluded from the entire original disk union in this case. This does not establish that all remaining error is geometric, or that arbitrary recentering improves other cases.

The training-only zero-fit replication was source-frozen before preparation and used the same prespecified trigger as the after cohort: original KKT 0.000355950715, local radius 24.999999999999762 km, recentered KKT 8.072205293, outward derivative −11.010872146 objective/km and centered 0.1 m finite-difference derivative −11.010870949. The saved endpoint's solver initializer delta was zero. Root reviewed this actual numerical evidence before authorizing the fresh two-call protocol in `MODEL_C_BEFORE031_DISK_CONTROL_PROTOCOL.md`.

| Measurement | Original-disk repeat | Recentered disk |
|---|---:|---:|
| Objective | 34725.446723416404 | 33519.04376051027 |
| Training NLL | 34485.10567544194 | 33287.88705148193 |
| Posterior RMS Hz | 111.500991431 | 99.818043856 |
| Independent own-domain KKT | 0.000353620599 | 0.000084582050 |
| Evaluations | 20 | 259 |
| Original fitter elapsed s | 0.660317 | 9.641064 |
| Configured-reference error km | 26.287028736 | 10.221272805 |

The original repeat reproduces the source position and objective to numerical precision. Recentered objective improves by 1206.402962906 and NLL by 1197.218623960; posterior RMS improves by 11.682947575 Hz. These frequency measurements are training diagnostics, distinct from the position comparison. No held data was prepared. The reference remains the existing configured receiver location, not an independently surveyed location established by this experiment.

Both calls copied the exact same saved vector and nuisance. Original model, observations, bank, calibration, full priors, timing/epoch orbital prediction, fitted c, 20 s and 600 iteration caps were retained. The new geographic endpoint `[-77.035766108,-83.107919314]` moved 16.168868978 km and is interior to the new disk. Source and effective initial vectors were identical in both calls; no alias relift, half-view correction transfer, extra incumbent, retry or reference selection occurred. Original discovery/initialization/54-call costs were already incurred; this is an additional matched warm control, not equal end-to-end search cost against the baseline.

The complete two-call slice took 23.241392992 s including 12.781307756 s validation/preparation and independent replays, below 120/135/140 s internal/TERM/KILL bounds. Five prerequisite workers, A/root scientific work and unrelated host analysis ran concurrently. Both outcomes were sealed before the configured-reference evaluator loaded its reference. Both independent endpoint objective/NLL/stationarity replay deltas were zero. Three owned control tests and Ruff passed, including exact starts/caps, retained timeout, unexpected exception, source tamper/no-retry and the paired reference gate; the original core geometry/trigger tests remain the numerical oracle coverage.

Implementation/protocol commits: ce141bf51 (zero-fit replication) and 3bb7017b1 (matched control). SHA-256 receipts under `local/`:

| Receipt | SHA-256 |
|---|---|
| `model-c-domain-before-031-v1/protocol.json` | `751631425c9ee3bce2b1f124327b20f2f692f4a5cfec989184a18e436c248cdb` |
| `model-c-domain-before-031-v1/result.json` | `79d4cdaef0a749c30800c5971b650fba8dd58bb40c61198e9ffa2344d8d13760` |
| `model-c-domain-before-031-v1/termination.json` | `78ed384bd4bc5719e09ec62e094fa0962cfd8b70b6031a951424d37efc3c6e89` |
| `model-c-domain-before-031-control-v1/protocol.json` | `b444b1676c87fcd11b8127a5fdc70db640666bd09fc0509ec7688bd34a9661db` |
| `model-c-domain-before-031-control-v1/terminal.json` | `54d2278f41c42d7074d9f170e45a83269f0f03006f7a5b0056ee85c8ebbaa0d7` |
| `model-c-domain-before-031-control-v1/seal.json` | `a90a202124ff4dd33d62b9a693c4200945b81e3ac084a9b261c360fd496d600a` |
| `model-c-domain-before-031-control-v1/termination.json` | `285c60e18e1acdc54d670419ea8495659e245185007e8b8c83986ce0f96922f4` |
| `model-c-domain-before-031-control-v1/development-errors.json` | `34fef3503f77deb1945fb45be8574c3489e34ba6ef4ce306260b9d67fe4a216b` |
