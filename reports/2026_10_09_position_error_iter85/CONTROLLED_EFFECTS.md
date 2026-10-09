# Controlled effects from deployed hard60

All148 recordings are included: DS16 63, DS17 51, DS18 34. These are consumed development results. No new deployment is implied.

Negative changes below mean lower position error. Each contrast is specified before execution. Refit controls isolate model changes from another local optimization, but the complete expanded-search pipeline has extra computation.

| Change | Fitted-c mean delta km | Improved/regressed/tied | c=0 mean delta km | Improved/regressed/tied |
|---|---:|---|---:|---|
| Search only | -2.788332 | 2/0/146 | -2.777201 | 2/0/146 |
| Joint clock only | -0.428792 | 104/44/0 | -0.382633 | 98/48/2 |
| Joint clock after expanded search | -0.446107 | 106/42/0 | -0.405591 | 99/47/2 |
| Pruning versus unpruned refit | -0.397241 | 51/30/67 | -0.312182 | 42/39/67 |
| Clock-prior relaxation versus narrow refit | -0.052783 | 81/66/1 | -0.008107 | 73/74/1 |
| RF time versus RF-off refit | -0.007900 | 87/60/1 | +0.000000 | 0/0/148 |
| Satellite slope0.25 versus RF refit | -0.039748 | 107/40/1 | -0.085635 | 102/44/2 |
| Satellite slope0.5 versus RF refit | -0.082542 | 100/48/0 | -0.158060 | 97/51/0 |
| Slope0.5 versus0.25 | -0.042794 | 96/52/0 | -0.072425 | 92/56/0 |

## Search and joint-fit interaction

Interaction = mean(B3) − mean(B2) − mean(B1) + mean(B0). Negative means the combined improvement exceeds the sum of the isolated improvements on this corpus. It is descriptive, not independent validation.

| Dataset | Fitted-c interaction km | c=0 interaction km |
|---|---:|---:|
| DS16 | -0.031032 | -0.034198 |
| DS17 | -0.011914 | -0.024378 |
| DS18 | +0.000000 | +0.000000 |
| Pooled | -0.017315 | -0.022958 |

## Accuracy and deployment limits

Frequency RMS, qualification, fallback and timing data are separate in [RESULTS.md](RESULTS.md) and summary.json. c0 locks RF-time coefficients; C5 fitted-c versus C5 c0 isolates static c, and B5 versus C5 fitted-c isolates RF time with static c enabled. All use shared fitted-derived candidate inputs.

No per-scan best-error combination is operationally selected. A subsequent frozen removal study must test which components remain necessary in the chosen combination. The reserve remains outcome-unexamined. Cold integrated replay, ordinary new-scan shadow results, fallback/runtime checks and WebUI PNGs are required before promoting a new default.

![Mean error by configuration](means.png)

![All-member error distributions](distributions.png)

![Individual scan errors](per-scan.png)
