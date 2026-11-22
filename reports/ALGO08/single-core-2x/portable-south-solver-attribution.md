# Where the southern portable-v5 solver comparison diverges

On the same southern saved detections, the installed solver improves its two signed fits by accepting a cavity reassignment of **443 observations from NORAD 61970 to 62508**. The covariance candidate reaches a signed fit with lower geographic error than the installed signed incumbent, then publishes it. Its error is higher than the installed result after reassignment. The first changed fit comes earlier, when covariance stops initial nomination after two phase refreshes and installation runs five. The first change in retained evidence is the length of three accepted salvage trims. [Stage and owner receipt](measurements/portable-south-solver-attribution.json.gz)

## First changed fit and first changed observations

Two instrumented saved-solver runs reproduced the recorded positions, RF RMS and owner digests exactly. Both used the same 25,000 ordered native probe opportunities, stored offered square and capture-time orbital archive. The Graph track digests and both causal sky contexts agreed. All three ranked curved assignments, their aliases and both first refreshes of each fixed-zero branch matched. Both chose the third ranked branch. At the two-refresh endpoint it was at east/north **−2.145 / −10.375 km** with squared residual **19,274.697**. Three additional initial refreshes moved the installed winner to **−0.779 / −11.328 km** and **19,225.163**. The initial gate rejected the same nine fragments and retained **3,534 points** in both paths. [Installed nomination](../../../tools/pipeline_eval/variants/v5_core.py) · [Collapsed nomination](../../../tools/pipeline_eval/variants/algo08_collapsed.py)

Installed conservative recovery refits the same curved mask before salvage. Covariance fits both arms with its warm, causal family likelihood first, then uses the fitted incumbent for salvage. Neither initial paired fit rejected any of the 3,534 points. The two salvage calls named the same five fragments with the same satellite labels. Their proposed lengths differed on four fragments. Both final repair paths rejected the short RX1 channel 7 fragment assigned to NORAD 64160. The other three length differences account for all support differences in the signed fits. [Installed conservative recovery](../../../src/leo/analysis/localization_v3/conservative_recovery.py) · [Collapsed salvage](../../../tools/pipeline_eval/variants/algo08_collapsed_salvage.py) · [Paired repair](../../../tools/pipeline_eval/variants/algo08_collapsed_repair.py)

| Changed retained fragment | Satellite | Installed points | Covariance points |
| --- | ---: | ---: | ---: |
| RX1 channel 3, T001 | 67125 | 123 | 165 |
| RX2 channel 3, T001 | 67125 | 164 | 191 |
| RX1 channel 7, T000 | 55352 | 144 | 129 |

The installed signed model had 4,122 curved and 27 predictive observations per arm. Covariance had 4,176 curved and the same 27 predictive observations. Both chose the same two predictive fragments and accepted the signed update, whose common qualified coefficient was **−0.1394616134**. Their paired fits saw different curved support and independently fitted nuisance terms. The trace localizes the first support split to salvage. It does not estimate the separate effects of nomination refresh count, the pre-salvage likelihood, or each individual trim. [Signed update](../../../src/leo/analysis/localization_v3/signed_context.py) · [Covariance signed adapter](../../../tools/pipeline_eval/variants/algo08_collapsed_signed_finish.py)

## Accepted complete-family cavity trial

Before the cavity, both signed models kept the same 221 and 222 observations on RX1 and RX2 channel 2 fragment T002 assigned to NORAD 61970. The installed cavity held out the family, nominated 62508 with a predictive gain of **138.026**, and adopted the reassignment after the original paired validation and objective comparison. Covariance retained 61970. The final maps have 4,134 common observation identities per arm. All 443 changes among those shared identities are the channel 2 reassignment. The remaining 3,691 common owners and roles match exactly. Covariance has 69 additional channel 3 observations and installation has 15 additional channel 7 observations. [Cavity nomination and adoption](../../../src/leo/analysis/localization_v3/family_cavity.py) · [Selection order](../../../tools/pipeline_eval/variants/v5_core.py)

| Fit | Fixed-zero east / north (km) | Fitted east / north (km) | Horizontal error, fixed zero / fitted (km) | RF RMS, fixed zero / fitted (Hz) |
| --- | ---: | ---: | ---: | ---: |
| Installed signed incumbent | −8.019 / −4.068 | −8.293 / −3.912 | 2.400 / 2.110 | 24.418 / 24.404 |
| Covariance signed and published | −8.766 / −3.410 | −8.928 / −3.398 | 1.429 / 1.339 | 24.472 / 24.429 |
| Installed after accepted cavity | −9.876 / −2.226 | −10.099 / −2.091 | 0.351 / 0.583 | 24.107 / 24.089 |

The accepted cavity moves the installed solution 2.616 km fixed-zero and 2.565 km fitted. It improves its own horizontal error by 2.049 and 1.527 km, respectively. This observed intervention explains the reversal between the signed-stage and published geographic comparisons. The installed reassignment was evaluated under the installed masks and powers. Whether the same family wins and qualifies starting from the different covariance incumbent remains an independent test. The covariance geographic guard bypassed this interior fit. The predictive-grid handoff runs after owner selection. [Covariance parent](covariance-publication.md) · [Predictive-grid scope](solver-posterior-handoff.md)

## Reproduce

The runner reuses the staged portable-v5 containing offer and its existing `native.json` and TLE data. It adds readouts at deployed and frozen solver boundaries and requires exact equality with each archived terminal result. It makes one saved solve per build and uses no raw I/Q. The numerical inputs contain the explicit region. Horizontal errors use the released `synthetic-labels.json` from public tree `9a9e4ebe50b9922f7e1443eadb840e3fec2b0b3d` only after the solves. Two component tests cover observation mask identity and per-observation owner differences. [Runner](portable_south_solver_trace.py) · [Tests](../../../tests/pipeline_eval/test_portable_south_solver_trace.py)

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/single-core-2x/portable_south_solver_trace.py \
  run "$bench/portable-v5-geodiverse" "$bench/integration-covariance-posterior" "$new_trace_directory"
```
