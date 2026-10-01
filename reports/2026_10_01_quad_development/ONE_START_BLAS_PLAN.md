# One-start plus BLAS acquisition: fixed composition pilot

Hypothesis: the previously verified matrix-product acquisition can reduce cost further when combined with one acquisition-ranked starting location, without changing the likelihood, proposals or fitted result. Separate speedup percentages must not be added to predict the composed runtime.

Before fitting, require the three sealed `one-start-blas-prerequisite-v1` checks to pass and their source/input hashes to verify. These compare every track's score and visibility mask at fixed prior points and original acquisition seeds, then compare the complete optimized proposal against the original saved acquisition. This prerequisite covers the first single of each dataset; it does not establish equivalence for pairs or quads.

The initial cold pilot contains DS9-B01-S1, DS10-B01-S1 and DS11-B01-S1. Two fresh-process arms per unit: original `run_seed_limit.py --seed-limit 1` and the composition wrapper `run_one_start_blas.py --seed-limit 1`. Both acquire anew and start nuisance coordinates at zero. The original worker, evidence, likelihood, prior, fixed 100 ft MSL height, 64-iteration limit and model remain unchanged. The wrapper only substitutes the acquisition function and preserves the process-start timer. No saved fitted state initializes either arm.

Fix orders before running: DS9 original then BLAS; DS10 BLAS then original; DS11 original then BLAS. Sequential execution under the existing shared lock, 90 seconds per inference and 90 seconds per separate numerical audit, no retries or threshold changes. Freeze source files, physical inputs and the original baseline receipt before launch; verify again after completion. Preserve every outcome, including deadline and proposal-equivalence failures.

Require exact proposal seeds, requested count, unique-point count and spacing across both arms and the saved original proposal; compare proposal scores at absolute tolerance 1e-6. Require one fit with configured seed limit one in each arm, fitted state agreement at 1e-5, exact assignment equality and final objective agreement at 1e-6, both across arms and against the saved original first fit. Run the original independent numerical audit before reporting geographic errors. No stronger location accuracy claim follows from equivalent fits.

Report cold wall and CPU time separately; startup/inference scope excludes original radio/orbit extraction, coordinator preparation and subsequent audit. One measurement per arm and fixed alternating order do not establish stable speed distributions. These scans have already been exposed in development and share an unsurveyed reference site.

Inspect all six outcomes before proposing a separate pair/quad extension. If equivalence fails, diagnose before expansion. If the composition saves no meaningful time, retain the simpler implementation. No production promotion is part of this pilot.
