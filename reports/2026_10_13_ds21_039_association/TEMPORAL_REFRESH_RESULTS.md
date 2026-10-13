# DS21-039 temporal refresh: negative sensitivity result

**The prescribed satellite refresh model worsened localization and native residual RMS. No promotion.** With fitted c in both conditions, sealed post-fit development error increased from **4.072515 km** to **4.410061 km** (**+0.337546 km**). Both conditions miss the 0.5 km target.

This is a temporal model sensitivity test. Receiver timing supports the proposed revisit links; recorded metadata does not establish same-emitter continuity. The original sticky satellite/cell graph was not activated. The new model carries satellite/clutter state only and marginalizes native ambiguity choices separately in each window.

| Selected condition | Error km | Native posterior RMS Hz | Signal window mass | Clutter mass |
|---|---:|---:|---:|---:|
| Original singleton baseline | 4.072515 | 92.162359 | 2167.247596 | 630.752404 |
| Satellite refresh linked | 4.410061 | 94.880863 | 2179.610524 | 618.389476 |

The linked model has a lower objective/NLL, but it defines a different joint likelihood. Comparing those cross-model scores does **not** establish better frequency quality. Its posterior native RMS rises by **2.718504 Hz**, and its separately evaluated position error also rises. Signal mass increases by 12.362927 windows without improved accuracy. The development reference is the configured station location, not an independently surveyed location in this work.

## Prescribed, matched test

Four fitted-c calls used the same two complete physical initializers: original all-training winner and the stationary winner of the original seven-call refinement. Each call had **20 s / 600 iterations**, within the same original **seed-5-centered 25 km disk**. The original ν2 group layout, native observations, bank, receive times, calibration frame and physical priors were preserved. The actual baseline fits used the unchanged original singleton model. New singleton arithmetic was used for source closure and diagnostics only.

The linked families use **RX/channel/exact RF/original counter-defined 20 s training block**, with **maximum gap 1 s** and prescribed **τ=1 s**. Its transition is `T(dt)=exp(-dt/τ)I+(1-exp(-dt/τ))ones*pi`, where pi is the original normalized satellite/clutter prior. This allows direct satellite/clutter switches and preserves pi as stationary; native candidate choice resets every window. Neither τ nor the gap was estimated or tuned to reference error.

Both conditions retain **2,798 original windows, 3,714 native candidates, and the same 43 satellites**. The linked inventory has **1,182 families / 1,616 edges**: **227 singletons, 294 pairs, 661 triples**. Edge gaps span **0.352244–0.712009 s**. Counter-derived block versus original window-time floor differs for **zero windows**. Blocks are the original training blocks; held/quarantined blocks provide no links.

Family window-ID inventory hash: `sha256:cc28b4dcc5b744b8315957e0e236629f56190a6f89d2aa8b5f16326d4d09dba5`.

## Four outcomes and selection

All four calls returned stationary fitted-c states. Selection used the minimum training objective separately within each condition. Baseline source incumbents were eligible; linked selection required a new stationary fit. Both selected states came from the refinement-free initializer. No reference entered fitting or selection.

| Call | Stationarity | Objective | Likelihood NLL | Fit seconds | Evaluations | Distance from seed 5 km |
|---|---:|---:|---:|---:|---:|---:|
| baseline-original-all | 5.357e-4 | 33172.423429 | 32969.499770 | 0.551 | 21 | 9.292923 |
| baseline-refinement-free | 7.042e-5 | 32380.954535 | 32225.181022 | 0.750 | 29 | 9.369240 |
| linked-original-all | 3.347e-5 | 28735.557290 | 28539.988407 | 16.429 | 240 | 8.922415 |
| linked-refinement-free | 8.062e-5 | 27845.883933 | 27691.819722 | 14.913 | 218 | 9.658558 |

Each call stayed within its 20 s budget and the original parameter bounds. All vectors retain **50 physical coefficients + two group nuisance coefficients**, no RF contrast tail or extra clock fields. Recorded physical-constraint minima are feasible. Total runner time was **33.386715 s**; the root wrapper reported 60.5616 s including preparation, within the frozen 165/175/180 s internal/TERM/KILL limits.

## Independent receipt audit

The audit performed byte-hash checks and arithmetic on saved receipts only. It made **zero inference/optimizer/IQ calls** and did not read the reference-source module. The authorized sealed development evaluation receipt was read after the final fit seal existed.

- **329** frozen source files match both live bytes and archived bytes; all **six ancestor bindings** match the original input and seven-call refinement authority.
- Both initializer source oracles pass actual old-versus-new singleton cost, complete gradients, satellite/clutter/native posterior, and native gradient closure. Historical objective/NLL replay deltas are **exactly zero** for both parents.
- Across both oracles, maximum cost/NLL delta is **5.820766e-11**, vector gradient delta **3.673203e-13**, nuisance gradient delta **1.075529e-16**, native posterior delta **5.551115e-16**, and native gradient delta **1.040834e-17**.
- Native posterior/gradient comparisons include the complete inventory. Conditional residual ratios are checked on normal posterior mass only; the receipts disclose zero/subnormal pairs separately because such ratios are rounding-sensitive. Their maximum checked delta is **9.094947e-13 Hz**.
- Exactly four launch, termination, attempt, and per-attempt seal receipts are present. All hashes and the **21-file final seal** pass. The audit independently reproduces stationarity/geometry decisions and within-condition minimum-objective selections.
- Selected objective/NLL and physical prior ledgers close within **1e-7**. The saved evaluation binds the exact sealed terminal and freeze. Its file timestamp follows the final seal; freeze/protocol/terminal declare no reference or held use during inference.

Machine-readable bindings, all four outcomes, per-parent oracle deltas, limits and unrounded metrics are in [TEMPORAL_REFRESH_RESULTS.json](TEMPORAL_REFRESH_RESULTS.json). The terminal authority is `sha256:5837810fb7d6f080dd06e2460ef8e575310ea221e1c008938ea1c6190f2057fb`; final seal is `sha256:149c0d5f0c4a46ab1820bdadf2347dbbe9a11d47697892600729ffd686fa4019`.

This bounded result rejects promotion of the tested temporal assumption. The original scientific modules and frozen receipts remain unchanged; historical zero-c artifacts remain unchanged.
