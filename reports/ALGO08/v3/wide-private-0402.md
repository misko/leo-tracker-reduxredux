# Wider private likelihood blocks on saved DS30-0402

The wider retry reduced the fitted-first named solver from **51.471 to 45.237 CPU seconds** and the complete saved publication from **55.830 to 49.712 seconds elapsed**. All **239** original unsupported likelihood calls used the wider implementation, with no secondary fallback. Both final positions and RF fits, every ordered owner and role, the 179-point grid and path, and all eight PNGs matched the named publication. [Frozen protocol](wide-private-0402-protocol.md) · [Capture and scored publication receipts](measurements/wide-private-0402.json.gz)

## Why the original likelihood fell back

The sampling pass ran the original fitted-first route through selected evidence. The stock likelihood paid **7.521 CPU seconds** for the 239 unsupported calls. For each of four observed shapes, the first genuine call supplied its original design, noise-group labels, priors and update budget. Each sample had a group with **five columns private to that group**. The stock C layout accepts up to two. Two conservative-fit samples had two width-five groups each. Both cavity-fit samples had one. The unchanged size and Gram-slot limits passed. The complete wider replay activated every rejected stock call after relaxing only the private-width limit, confirming that these calls encountered that limit. [Stock likelihood source](../../../src/leo/analysis/localization_v4/native_bound.c) · [Earlier 0402 named profile](named-roster-0402.md)

| Original scope | Rows × columns / groups | Observed calls | Stock CPU s, all calls | Same-input median stock → wider CPU ms |
|---|---:|---:|---:|---:|
| Conservative curved fit | 4,494 × 234 / 97 | 38 | 1.524 | 53.426 → 12.887 |
| Conservative curved fit | 4,494 × 235 / 97 | 41 | 1.769 | 56.939 → 13.466 |
| Cavity configuration | 4,150 × 236 / 85 | 80 | 2.117 | 26.484 → 6.416 |
| Cavity configuration | 4,150 × 237 / 85 | 80 | 2.112 | 26.800 → 6.476 |

The existing width-eight implementation factors each larger private block and eliminates it before the shared Schur solve. The original observations, group weights, priors, stopping threshold, budget and condition checks remain in force. All twelve sampled wider calls activated. Each sampled result preserved its robust update count with maximum differences of **5.82 × 10⁻¹¹** in negative twice ELBO and **1.28 × 10⁻⁷ Hz** in conditional residuals. Pricing the entire observed call budget with the four measured ratios gives **5.712 CPU s** of estimated savings. Rows with the same dimensions can have different support masks. The full replay actually built six symbolic layouts and reused them 233 times. [Wider implementation](../../../tools/pipeline_eval/variants/algo08_private_width.py) · [Private factorization](../../../tools/pipeline_eval/variants/algo08_private_width.h) · [Earlier dense and southern measurements](../single-core-2x/solver-wide-private-blocks.md)

## Paid complete saved replay

| Boundary | Archived fitted-first | Fitted-first and wider layout | Saved |
|---|---:|---:|---:|
| Solve CPU | 51.471 s | 45.237 s | 6.234 s |
| Solve elapsed | 51.496 s | 45.249 s | 6.248 s |
| Through exit CPU | 55.802 s | 49.698 s | 6.104 s |
| Through exit elapsed | 55.830 s | 49.712 s | 6.118 s |

The original likelihood ran on supported calls and on all selected-packet and grid reconstruction. The fitted arm still completed five constrained rounds and rejected the same two conditional gates after 58 visits. Neither rejected unconstrained proposal changed its gate outcome or failed-track counts. The wider arithmetic changed their unpublished corrected objectives by at most **3.75 × 10⁻⁹**, RF RMS by **4.53 × 10⁻⁹ Hz**, and final phase-change diagnostics by **7.58 × 10⁻¹¹ s**. The paired terminal retained **100.672203 / 100.576460 Hz** RF RMS and **0.863651 / 0.860302 km** horizontal error for `c = 0` and fitted `c`, respectively. Both arms retained **4,821** ordered owners. The terminal digest, rank, numerical sidecar digests and position-PNG bindings all matched. The verifier independently decoded all eight PNGs and reproduced their original dimensions and encoded and decoded hashes. [Fitted-first control](constrained-pair-arm-order.md) · [Historical scores and signed packet](prospective-0402-solver.md)

The studies ran on the same low-priority single-core Gauss slot with the original saved input, archive and offer. The candidate and archived fitted-first timing both recorded zero filesystem input blocks. They are separate sessions, and the four-call sample covers the observed shapes of this recording. Sixteen focused tests passed. The two paid workers used `820d7a97a`. The first stopped at selected evidence and took **48.021 s** through exit, including its build and kernel trials. The second was the sole complete candidate. [Driver and independent scoring](wide_private_0402.py) · [Component tests](../../../tests/pipeline_eval/test_wide_private_0402.py)

Use `wide_private_0402.py capture NEW_TMPFS_ROOT` under the locked release environment. The retained build and sampling receipt are `/dev/shm/leo-v3-0402-width-capture01/exact`. Run `wide_private_0402.py replay NEW_TMPFS_ROOT CAPTURE_ROOT/exact` only with its verified viable capture. `evaluate RUN_ROOT NEW_RECEIPT.json` checks the complete solved artifacts against the named control.
