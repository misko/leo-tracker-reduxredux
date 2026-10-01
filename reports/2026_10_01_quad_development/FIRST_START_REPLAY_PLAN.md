# Expanded-panel first-start accuracy ablation

## Question and hypothesis

Do the extra acquisition starts improve accepted geographic accuracy enough to justify their cost across the 64-single / 32-pair / 16-quad development panel? The earlier original64/DS12 ablation favored a one-start simplification, but the expanded-panel screen shows material differences between available modes. The DS9 cold gates isolate implementation and runtime behavior; one block cannot establish panel-wide accuracy.

The hypothesis is that the highest acquisition-ranked start often suffices, while later starts sometimes improve the fitted objective without improving reference error. This hypothesis can fail: one start may reject more windows or worsen error materially, especially in the quad tail. Do not select the policy by individual reference errors.

## Fixed population and selection

Use all 112 windows in the existing sealed `selection.json`, with each original `independent-v2` receipt. For every window choose `fits[0]`, independent of its objective, convergence or geography. Preserve a missing, unresolved or unauditable first fit as a failure. No fallback to another start, no continuation and no refitting. Select neither a geographic subset nor a subset of successful outcomes.

Compare against the original three-start selection and its original audits, not the continued baseline. Comparing against continuation would confound start count with extra optimization. Keep the separate continued baseline available as context only. This is a replay of saved first fits and not a fresh cold pipeline result or new training data.

## Required evidence

Preserve immutable original receipts. Any derived receipt must explicitly record its parent hash, selected start index, replay qualification and original recorded fitting work. A new process launch measures only replay materialization, never inference cost. Perform the existing independent numerical audit against prepared physical inputs: state support, assignments, objective, monotonicity, finite-difference gradient and stationarity. Do not inherit the original winner's acceptance merely because the first fit reports convergence or has a close objective. Record each audit process and failures, then read reference coordinates only for audited outputs.

Verify source and input bindings before replay and during audit. Any scientific source change requires a versioned implementation; no modification of the frozen original runners or receipts. First run the seven DS9-B01 windows as an implementation check, then process the remainder in bounded block batches if provenance and audits behave as specified. Cases failing the numerical test remain outcomes rather than causing replacements or retries. Use the shared lock and one audit process at a time; no RF collection.

## Reporting

For each window size report accepted/planned, conditional median/p90/max error, within-1-km and within-3-km counts with all planned cases in the denominator, and matched error changes on jointly accepted cases with asymmetric failures explicit. Separate datasets. Preserve block correlation in comparisons; do not call the 112 overlapping windows independent trials.

Plot matched first/selected reference errors and summarize the saved fitting work omitted separately from the measured cold-gate timings. No new cold speedup claim follows from replay bookkeeping. This experiment evaluates a simpler search policy; it does not modify nuisance priors, hard association, visibility, residual likelihood or acquisition arithmetic. Promotion requires weighing the complete accuracy/failure tradeoff and additional geographic validation; no acceptance or error threshold will be relaxed after viewing outcomes.
