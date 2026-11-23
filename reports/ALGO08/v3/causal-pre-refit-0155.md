# Causal warm refit within the named DS30-0155 solve

Using the named solver's earlier curved pair to initialize its predictive fit preserved all **3,498 ordered owners and roles** in each calibration arm. The predictive pair took **0.352 instead of 1.382 CPU s**, including initialization, with no fallback. The complete saved publication went from **24.905 to 23.292 s** through exit. The fit changed numerically. The fixed-zero endpoint moved **16.26 m** and the fitted endpoint **7.03 m**, both within the frozen local 20 m screen. [Frozen protocol](causal-pre-refit-0155-protocol.md) · [Sealed saved pair](measurements/causal-pre-refit-0155.json.gz)

| Calibration | Cold horizontal error | Warm horizontal error | Cold RF RMS | Warm RF RMS | Endpoint displacement |
|---|---:|---:|---:|---:|---:|
| `c=0` | 0.972393 km | 0.957039 km | 155.420160 Hz | 155.421673 Hz | 16.257 m |
| Fitted `c` | 1.156875 km | 1.152637 km | 155.382354 Hz | 155.382952 Hz | 7.032 m |

Both processes used the genuine full named-v3 20 ms packet, original region and causal archive, along with the same exact Graph, exact forecast preparation and corrected Cairo renderer. The cold control reproduced the archived named positions, RF residuals, ordered owners, numerical path and grid science exactly. The only within-pair numerical option was the warm predictive refit. It takes the original history policy's 3,069 curved and 429 offered predictive observations and initializes each calibration from its own preceding qualified curved endpoint and clipped posterior phases. It retains the named roster, aliases, phase prior means, weights, robust model and all later gates. Both warm arms finished in two phase refreshes. The original fit uses five. The original downstream policy adopted no signed-phase adjustment and offered no cavity alternatives on either run. [Warm pair and charged fallback](causal_linear_refit.py) · [Earlier exact preparation and renderer](named-weak-exact.md)

| Saved boundary | Named cold | Causal warm |
|---|---:|---:|
| Both predictive refits and warm initialization, CPU | 1.382 s | 0.352 s |
| Complete numerical solve, CPU | 22.143 s | 20.583 s |
| Complete render, CPU | 1.331 s | 1.292 s |
| Process exit, elapsed / CPU | 24.905 / 24.891 s | 23.292 / 23.287 s |

Seed construction itself took 0.098 ms CPU and is included in the 0.352 s attempt. The directly measured local fit saving is **1.030 CPU s**. The numerical and process differences also reflect variation in other stages and dependencies. The cold process incurred 672 input blocks and four major faults, while the warm process recorded zero. The earlier original named publication exited after 25.571 s under a different preparation and renderer. Both fresh runs completed under one shared low-priority Gauss CPU2 slot with one numerical thread. All original input was already staged in tmpfs, with zero original waveform calls or bulk archive reads. These are saved publication clocks. [Timing runner](causal_pre_refit_0155.py)

Both fits published the full 179-point numerical grid and path, with each sidecar bound to its own actual position PNG. The warm path and grid differ from the cold output. There are 81 shared grid coordinates and 98 unique coordinates in each grid after the endpoint-dependent samples moved. Every shared coordinate's score changed in both arms, with maximum absolute normalized-objective differences of 0.15711 and 0.02393. All eight encoded files and decoded RGBA images were verified, and dimensions matched. Their bytes and pixels differ across fits. Both renditions used four native orbit sheets and two native residuals without fallback. Each Cairo legend exactly matches the independently reconstructed set of 18 fitted owner satellite labels plus the unassociated label, with a 26 px minimum gap. This case preserves roster and stays within the local position tolerance. It provides a bounded numerical comparison on this one recording. [Numerical and media evidence](measurements/causal-pre-refit-0155.json.gz)

The separately frozen DS30-0160 transfer retained its original owners and history retry, and passed the same 20 m endpoint screen. Its shorter predictive fit did not reduce complete saved elapsed time. [History retry transfer](causal-pre-refit-0160.md)
