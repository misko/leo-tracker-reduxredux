# Information-weighted visits for a full-data warm start

The weighted rule improved a measured exposure proxy over equal-size uniform-in-time blocks on both saved inputs. On dense DS30-0008, however, the optimistic warm-start ceiling was **1.499 CPU seconds** before any subset-fit or verification cost. The exact-trust version had a **0.693-second** ceiling. Both fall below the prespecified two-second gate. This study ends at the archive screen, without a new nonlinear fit or location claim. [Frozen protocol](visit-information-warm-start-protocol.md) · [Receipt](measurements/visit-information-warm-start.json)

## Equal visit count, different exposure

Both rules select blocks of eight consecutive admitted stereo visits across the recording and preserve its full time span. The uniform control chooses closest to each hardware-time midpoint. The weighted rule chooses the block with the greatest weaker-arm log determinant after fitting a nominal nuisance design. The inputs are three observable proxy columns from time and signed carrier, four receiver-band baselines, four receiver-band drifts and the measured RF term in the fitted-`c` arm. The selection includes all eligible signed alternatives within a lane while giving each positive lane at most one unit of weight. It reads no offer geometry, satellite labels or survey. Higher proxy information does not establish better horizontal information or a better warm start. [Selection and signed-source checks](visit_information_warm_start.py)

| Saved observations | Stereo visits | Verified signed factors | Weakest-direction proxy, `c = 0` / fitted `c` |
| --- | ---: | ---: | ---: |
| DS30-0008, full | 6,765 | 7,336 | 100% / 100% |
| DS30-0008, uniform | 2,269 | 2,440 | 32.99% / 33.00% |
| DS30-0008, weighted | 2,269 | 3,044 | 40.58% / 40.59% |
| South, full | 1,200 | 456 | 100% / 100% |
| South, uniform | 400 | 148 | 29.28% / 29.30% |
| South, weighted | 400 | 164 | 35.61% / 36.19% |

The dense weighted view overlaps the uniform view on 621 visits. Most of its factor gain comes from receiver 0 channels 1–4 and receiver 1 channels 1–4, where counts increased from 535/487 to 834/764. Counts rose more modestly on channels 5–8, from 849/569 to 860/586. South had 37 uniform and 41 weighted factors in each receiver-band group. These are all native factors on the selected visits, without a graph or satellite association. Weighted selection raises the dense factor fraction to 41.49% from 33.26%, so it also leaves more rows for a putative subset fit. [Per-group counts and selected-visit digests](measurements/visit-information-warm-start.json)

The South containing and 100 m omitted requests have byte-identical authenticated detections. The corresponding visit selections and proxy values were identical across both offers. On the already published full comparison, the containing offer fixed with horizontal errors **0.817/1.101 km** and RF RMS **6.502/6.392 Hz**. The omitted offer falsely fixed with errors **0.817/1.102 km** and RF RMS **6.502/6.392 Hz**. The full-data geographic checks therefore remain necessary, and agreement with their existing omitted decision would reproduce a false fix. The archived survey outcome was read after the exposure selection. [Original South near-edge comparisons](named-south-transfer.md)

## What an ideal warm start could replace

The bound gives away original intermediate residual calls after keeping the full rank, every paid original owner-and-alias hypothesis, each fit's original starting evaluation and final exact derivative checks, and all later fit and geographic evidence work. The strict column leaves all original trial scores payable. The generous column grants a free, already-successful warm path and gives away early trial residuals as well. A real route also has to fit the subset, verify each original candidate with the original observations, and fall back to the ordinary full solve on unresolved comparisons. These are different timing scopes from the earlier experiments that shortened discovery itself. [Archived optimizer requests](optimizer-quadrature.md) · [Budget arithmetic](measurements/visit-information-warm-start.json)

| Original optimizer scope | Free nonfinal derivative calls only, CPU s | Free early warm trajectory, CPU s | Exact starts and final derivatives still payable, CPU s |
| --- | ---: | ---: | ---: |
| Dense cold, `c = 0` | 0.382 | 0.925 | 0.356 |
| Dense later, `c = 0` | 0.156 | 0.288 | 0.495 |
| Dense later, fitted `c` | 0.155 | 0.285 | 0.635 |
| **Dense total** | **0.693** | **1.499** | **1.486** |
| **Weak DS30-0016 total** | **0.038** | **0.070** | **0.060** |

The exact dense mixed-aperture clock independently left 1.470 of 5.908 cold CPU seconds outside its 4.438-second rank. A separate instrumented complete replay produced the residual timings above. Even granting perfectly linear cost with detector factor count and unchanged proposal request counts, the dense 2,269-visit view projects **0.877 CPU seconds** of gross early savings for weighting and **1.001** for uniform. Paying the measured dense choice computation of 0.041 CPU seconds leaves approximately 0.836 seconds for weighting before full verification or retries. Every fallback adds the proposal cost to the ordinary route. The factor model is an optimistic illustrative cost allocation. It does not model track repartitioning, fixed work, prior dimension or different iteration counts. The combined archive screening job used 0.139 CPU and 0.140 wall seconds. [Dense cold clocks](cold-exact-budget.md)

Earlier per-track 16-knot warm starts paid three restored full-data finalist fits and lost 65 owners on DS30-0374. The final full-data winner had ranked third on the sampled objectives. A broader quadrature route failed both dense calibration arms after restoring observations, and its 450 exact local reassociation checks found no qualifying repair. Those trials change nomination, where the larger time budget still sits. This whole-visit protocol instead keeps the original nomination untouched. The specially altered causal dense packet previously produced a 9.915-second optimizer trace on one losing branch. That hard-case evidence suggests a possible scoped warm-start question when the protected optimizer really dominates, while providing no transferable timing credit on the current unfiltered route. [Earlier sampled start](../single-core-2x/solver-sampled-initial.md) · [Dense quadrature and fallback](track-quadrature.md) · [Local reassociation](quadrature-local-repair.md) · [Hard derived-packet branch](finalist-rejection-bound.md)

To reproduce, run `visit_information_warm_start.py NEW_RESULT_JSON` with the frozen release virtualenv, this checkout's `src` on `PYTHONPATH`, the shared Gauss lock, CPU 2, nice 15, best-effort I/O priority 7 and one numerical thread. The script binds the retained `/dev/shm` native packets and archived timing receipts. It does not read original recording data. Three focused tests cover equal visit budgets, fixed endpoints, signed alias wrapping, per-lane weighting and disjoint timing arithmetic. [Tests](../../../tests/pipeline_eval/test_visit_information_warm_start.py)
