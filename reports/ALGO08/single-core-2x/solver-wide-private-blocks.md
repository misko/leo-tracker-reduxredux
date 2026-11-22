# Wider private blocks in the dense likelihood

The released native layout accepts two nuisance columns that belong to only one track group. All 83 dense Python fallbacks on corrected DS30-0008 hit this layout limit with five private columns. A research Schur backend supporting up to eight private columns handled all 83 and preserved both published fits, all observation owners, the numerical grid, and the optimizer path exactly. On the southern African containing simulation it handled 40 of 80 layout rejects. The other 40 still used the dense fallback after the wider factorization’s conditioning check. Both southern fits and full scientific evidence matched. [Measured receipts](measurements/solver-wide-private-blocks.json)

## Why the dense workload is expensive

The ordinary control without diagnostic capture used **54.96 CPU seconds on DS30 and 35.14 seconds in southern Africa**. The wider solver used **56.15 and 35.60 seconds**, respectively. Both comparisons retained the full position evidence. The faster isolated kernel therefore earns no complete-solver speed credit in the end-to-end budget. [Plain controls and terminal digests](measurements/solver-wide-private-plain-controls.json)

One capture per workload used the frozen restored-scout solver `ad417aaa…`, with the actual corrected physical detector document and the released southern containing detector document. The capture verified both controls against their already reported outputs and recorded every likelihood call’s status, dimensions and update count. [Capture runner](dense_likelihood_capture.py) · [Physical profile and binding](restored-scout-0008-solver-profile.md) · [Southern comparison](screened-stock-salvage.md)

- DS30-0008’s width-five fallbacks all came from `NormalPosition`, with 4,082 rows, 242 or 243 columns, and 103 groups. These 83 calls ran 2,294 updates and used 5.544 CPU seconds at the likelihood port. The southern control had 80 width-five layout rejects and 444 separate numerical conditioning fallbacks.
- The physical native burden concentrates in 99 calls with 4,522 rows, 249 or 255 columns, and 111 groups. They executed 18,750 updates and used 7.861 CPU seconds at the port. For the 256-update witness, LAPACK used 39.9 ms of a 107.6 ms stock call. Mean and residual evaluation used 23.7 ms, cross-covariance and conditioning 15.8 ms, primal norm and Schur updates 13.0 ms, assembly 7.7 ms, and variance and rate updates 6.3 ms. This is one representative input from the original 14.099-second native C budget. The southern native `NormalPosition` witness used 38 updates and took 6.7 ms. [Native timing instrumentation](dense_likelihood_kernel_trial.py)

## Wider private elimination

The prototype retries only the stock unsupported-layout path. It factors each wider private block with LAPACK, eliminates it before the shared posterior factorization, and reconstructs the group’s moments for the same Gamma updates. It retains the original observations, ordering, priors, full-design checks, convergence tolerance and update budget. Unsupported widths and failed conditioning use the original dense fallback. The new branch uses different floating-point factorization from the dense Python solver. The same captured kernel inputs establish numerical differences separately from complete solver parity. Earlier work eliminated independent components among shared columns or reused fixed Gram entries; this change addresses the private block size that prevented native execution. [Prototype](../../../tools/pipeline_eval/variants/algo08_private_width.py) · [Native factor](../../../tools/pipeline_eval/variants/algo08_private_width.h) · [Earlier shared-factor work](solver-native-family.md) · [Ordered Gram reuse](solver-fixed-gram.md)

| Captured width-five call | CPU, dense → wider | Stock and wider updates | Absolute ELBO change | Maximum residual change |
|---|---:|---:|---:|---:|
| DS30-0008 | 128.38 → 29.13 ms | 65 | 8.73 × 10⁻¹¹ | 1.75 × 10⁻⁸ Hz |
| Southern containing | 11.27 → 5.73 ms | 30 | 1.71 × 10⁻⁹ | 2.66 × 10⁻⁸ Hz |

Kernel timings are medians of five alternating calls on each captured input. All captured already-supported calls and numerical conditioning fallbacks retained byte-identical outputs. Six component tests covered supported, extended and oversized private widths, matching moments and stopping updates, and preserving the existing numerical fallback. [Component tests](../../../tests/pipeline_eval/test_algo08_private_width.py)

## Complete saved solves

| Saved input | CPU, captured control → wider | Elapsed, captured control → wider | Wider activations / attempts | Matched owners per arm | Fixed-zero / fitted horizontal error |
|---|---:|---:|---:|---:|---:|
| DS30-0008 | 62.810 → 56.152 s | 63.767 → 60.411 s | 83 / 83 | 4,472 | 1.639 / 1.512 km |
| Southern containing | 35.461 → 35.596 s | 36.012 → 35.899 s | 40 / 80 | 4,149 | 0.351 / 0.583 km |

Both replays retained the completion decision and reason, fixed-zero and fitted position and Doppler RMS, every observation-ID→satellite mapping, all scored grid nodes and path coordinates, and the exact endpoint objective replay. The physical RMS stayed 129.703040 / 129.662931 Hz and the southern RMS 24.106790 / 24.089107 Hz. The southern posterior grid also retained its 178 checked factor handoffs and 178 existing dense evaluations. Different conditioning behavior limited activation outside the physical input. [Complete paired checks](measurements/solver-wide-private-blocks.json)

The 6.658-second physical CPU difference exceeds the old fallback’s entire measured 5.544 seconds. The control copied representative inputs and recorded call metadata, while the wider replay recorded only its activation counters. Run variation and instrumentation prevent attributing the whole difference to wider blocks. There was no measured southern CPU gain. Even fully eliminating the measured physical fallback cost would leave most of the 21.423-second full-publication CPU shortfall. The next large native workload in this evidence is factorization and covariance work across the 18,750 repeated updates in the two dense layout shapes. [Original publication shortfall](restored-scout-0008-solver-profile.md)

## Reproduction

To time the ordinary control, run the same `guarded_solver_profile.py NATIVE SPEC ARCHIVE OFFER OUTPUT` command as for the wider variant, omitting both the optional profile path and `--private-width`. In this comparison the wider run preceded the plain control at each location. The DS30 wall clocks were 55.69 s for the plain control and 60.41 s for the wider solver. Southern wall clocks were 35.75 and 35.90 s. These are single pairs in separate processes. The chart runner checks both outputs against the archived positions, RMS, owners, grid, path and endpoint evidence. [Chart runner](plot_saved_location_speed.py)

Use the bound detector, specification and offer from the physical profile, or the released southern containing archive and detector. Run all commands with the same Gauss lock, CPU 2, `nice -n15`, `ionice -c2 -n7`, and one numerical thread as in the physical profile. `dense_likelihood_capture.py` accepts `NATIVE SPEC ARCHIVE OFFER NEW_CAPTURE` inside the frozen runtime. `dense_likelihood_kernel_trial.py STOCK_BINARY DIAGNOSTIC_LIBRARY OUTPUT CAPTURE...` profiles the saved native calls. Its `--wider` mode instead compares a separately built `private_width.so` with stock on those same calls. Build it with `algo08_private_width.build(NEW_DIRECTORY)` in the release Python environment. Invoke the existing `guarded_solver_profile.py` on each saved input with `--private-width NEW_DIRECTORY/private_width.so` and omit the optional profiling file for the whole-solve timing. This experiment changes no release or frozen publication binding. [Physical staging and lock](restored-scout-0008-solver-profile.md#reproduction)
