# Exact arithmetic in current cold finalists

The realized one-coordinate forward probes offer at most **0.378 CPU s on DS30-0402** and **0.143 CPU s on DS30-0374** in the measured geometry and initialization scopes, before charging any cache or data movement. The original optimizer already holds every base residual. Across 138 actual perturbations, no perturbed point recurred within its own model and the east and north probes in every pair differed on both coordinates. Giving away the *entire* original calculation at each other exact repeat would save 0.488 and 0.222 CPU s. We stopped at measurement. [Frozen protocol](cold-kernel-price-protocol.md) · [Sealed measurements](measurements/cold-kernel-price.json.gz)

| Measured cold work | DS30-0402 | DS30-0374 |
|---|---:|---:|
| Ordered full-catalogue rank, CPU s | 3.760 | 2.263 |
| Original saved complete cold trace, CPU s | 6.875 | 3.960 |
| Stock native Gamma in measured finalists, CPU s | 2.068 | 1.123 |
| Exact Gamma shadow calls / robust updates | 200 / 5,256 | 138 / 5,939 |
| Forward probes / probes with already known base | 80 / 80 | 58 / 58 |
| Entire forward-probe calculations outside the Gamma adapter, CPU s | 0.349 | 0.131 |
| All forward-probe C setup, group Gram and prior initialization, CPU s | 0.029 | 0.012 |
| Exact repeated objectives, excluding six endpoint calculations per case, CPU s | 0.400 | 0.157 |
| Shadow residual-energy phase, CPU s | 0.537 | 0.246 |
| Shadow residual energy at unique calculations, CPU s | 0.456 | 0.208 |
| Shadow LAPACK phase, CPU s | 0.663 | 0.379 |

The forward bound gives away Python work outside the Gamma adapter, including operations whose operands change, and gives away all C setup and initial moments for those calls. The measurements remove the shadow execution itself and retain observer overhead. Identical coordinates across immutable model instances receive zero credit because each finalist and phase refresh can have different design and nuisance state. A complete objective uses independently reweighted robust covariance and residuals even when an initial design column agrees. Prior same-assignment centre caching would address a separate small set of calls from ranking and was already priced on the dense mixed packet. [Centre and assignment reuse](dense-assignment-reuse.md) · [Exact cold budget](cold-exact-budget.md) · [Original cross-iteration Schur audit](../single-core-2x/solver-anderson.md#exact-schur-reuse-audit)

The measured 0.537 s residual-energy loop includes stage timers. Saving 0.5 s from that loop alone would require more than a 93% reduction with zero setup. Packing active design columns leaves mandatory per-row residual, noise division and ordered energy accumulation. After discounting work on the 32 exact repeat calculations, the whole remaining loop took 0.456 s. The larger LAPACK section operates on a Schur system that changes with each robust update. Adding the entire rank and optimizer savings would exceed the measured scope of any demonstrated reuse. The current rank remains the only multi-second cold component and separate earlier studies already tested centre geometry, mutable row substitution and approximate finalist tangents. [Earlier rank profile](cold-exact-budget.md) · [Finalist tangent comparison](finalist-tangent.md) · [Calibration-arm audit](cold-rf-schur-audit.md)

Both measured runs exactly reproduced the archived ambiguous-route result for three finalist prefixes, three completed fits, their objectives and selected cold position and phase reference. DS30-0402 selected branch 2 at 25,637.943822558977 and DS30-0374 selected branch 1 at 16,255.659622214525. The shadow agreed byte for byte on all 338 stock Gamma outputs, including returned rates and update counts. The saved jobs stopped at cold selection, which is upstream of the calibration pair, full roster and figures. Archived finished controls had respectively 4,821 and 2,822 selected observations per arm. These jobs did not revalidate final owner lists or position errors. [Observer](cold_kernel_price.py) · [Clock readout](cold_kernel_price_readout.py)

Through the cutoff, the two diagnostic processes took 16.607 and 10.558 s elapsed and 16.585 and 10.521 CPU s, including startup, verification, preparation, diagnostic compilation and shadow calls. Kernel shadow overhead was 2.092 and 1.138 CPU s. The first case charged 1,592 input blocks and six major faults across the process. The second charged zero of either. Both used the preexisting saved tmpfs scientific inputs, with waveform and original manifest reads disabled. The first worker launch stopped at an isolated validation import before cold after 0.436 CPU s. Its attempt is recorded separately. [Slot clocks and source hashes](measurements/cold-kernel-price.json.gz)

Run `cold_kernel_price.py launch NEW_TMPFS_PATH DS30-0402` and then `DS30-0374` with their own fresh output roots under the shared CPU 2, nice 15, I/O priority 7 slot and one numerical thread. The released venv runs the worker with `-IB`. For the outer launcher include the checkout, its `src`, the pinned payload and the pinned release source and root on `PYTHONPATH`. Pass the completed roots to `cold_kernel_price_readout.py` for validation and packaging. Four component tests passed. [Tests](../../../tests/pipeline_eval/test_cold_kernel_price.py)
