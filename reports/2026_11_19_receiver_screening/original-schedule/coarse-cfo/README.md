# Interleaving the original coarse CFO rows

Keep the full measured-plan 256 bank. Interpolating ten of the 21 complex CFO rows reduced median complete detector CPU by **33.28 ms** without repair, with exact ordered public output on **2/6** held visits. Direct shortlist repair restored **6/6** and increased median CPU by **13.76 ms**. The norm-envelope branch fell back on all **85 timed real grids** and added **206.67 ms**. [Stage chart](stage.pdf) · [Qualification](qualification.json) · [Protocol](PROTOCOL.md)

## Phase-centered interpolation and a sufficient ideal certificate

The compiled bank evaluates the 11 even CFOs at every original timing position and every 44-tap anchor. It shares the input FFT inside the block and centers each complex correlation at tap 21.5. Real, per-anchor least-squares weights approximate each omitted modulation from six nearby even rows or all eleven. The magnitude follows reconstruction. Both reference and sample normalization use the original support and frame accounting.

For normalized sample aperture \(x\), the reverse triangle inequality and Cauchy–Schwarz give \(\left||\langle x,h\rangle|-|\langle x,\hat h\rangle|\right|\leq\lVert h-\hat h\rVert_2\). Average these defects over the same valid anchor and frame terms to obtain a bound for each folded score. Direct repair computes all 44 taps and original normalization for each requested row and epoch. The selector requires the adjacent epoch scores that define a local peak. If every unresolved score's upper endpoint is strictly below the last exact retained score, every earlier or tied contender has already been classified and ranked with the original nonmaximum suppression. The strict inequality preserves cutoff ties and the original suppression order across rows. This proves the decision for enclosing score intervals in exact arithmetic. The prototype adds a declared floating-point allowance of `2e-6` to the ideal envelope. The observed agreement against the compiled prepared bank is finite numerical evidence.

| Interpolation terms | Largest support-averaged ideal defect | Largest observed score error | Candidate and neighbor cells at the already known original cutoff | Coarse keys before / after shortlist repair |
| --- | ---: | ---: | ---: | ---: |
| Six | 0.039381 | 0.001493 | 42,309–109,027 | 61/64 · 64/64 |
| Eleven | 0.011466 | 0.000444 | 574–4,790 | 64/64 · 64/64 |

These counts use eight development grids, the original eighth score already in hand and the ideal envelope without floating-point allowance. They count cells admitted by the cutoff-only test and include their neighbors. The six-term branch won the development selection on CPU after both orders recovered all 64 keys. Native six-term projection alone took 39.22/71.61 ms for 12/22 anchors against 48.00/90.37 ms for full 256. The instrumented repair and interval audit added around 17 ms per grid. [Development selection](selection-lock.json) · [Numeric stage table](stage.csv)

## What changed in the complete detector

| Method | Median paired CPU change vs full 256 | Median paired wall change | Exact public output | Exact ranked acquisitions |
| --- | ---: | ---: | ---: | ---: |
| Full 512 | +10.60 ms | +10.52 ms | 6/6 | 6/6 |
| Six terms, projection only | −33.28 ms | −32.18 ms | 2/6 | 1/6 |
| Six terms, shortlist repair | +13.76 ms | +15.27 ms | 6/6 | 6/6 |
| Six terms, interval check and fallback | +206.67 ms | +208.52 ms | 6/6 | 6/6 |

Each comparison uses 30 matched observations across six genuine visits from three capture producers. The underlying visits had authenticated full archive outputs. Projection-only retained all **20/20** physical fractional positives under the existing alias and epoch tolerances, with no extra positives. Exact public agreement also requires identical ranks, rejected candidates and numeric fields. The shortlist selected up to 32 provisional peaks and directly revisited a median 352 cells per grid. It reproduced every original ordered public field on the real panel and all eight empty, signed and near-equal controls. The bounded branch reproduced those fields through full scoring on the radio panel. [Per-visit decisions](decisions.csv) · [Paired times](timing.csv) · [Grid and repair counts](grid-receipts.json)

## Reproduction

Run `tools.pipeline_eval.qualification.coarse_cfo_eval` with `freeze`, `development`, `select` and `held` on the authenticated saved fixture workspace. Bind each replay to its original producer and one numerical thread on CPU 2 or 3. The projection-only diagnostic uses `tools.pipeline_eval.qualification.coarse_cfo_approx_eval`. `tools.pipeline_eval.qualification.coarse_cfo_results` reproduces the stage from those receipts. The preserved build files include the generated plan header and the compiled proposal for each order. [Input and software seal](input-lock.json) · [Evidence seal](evidence-lock.json)
