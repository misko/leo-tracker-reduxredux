# Cross-track batched stationary-offset prototype

## Outcome

The isolated prototype is numerically exact against the currently executed fast objective. `benchmark-v2.json` has zero objective and gradient differences at donor, interior, and sealed fitted points for frozen prefixes 1, 2, 4, and 8. Its four originally labeled near-boundary points were outside the active +/-12 km position bounds; they remain useful out-of-domain probes but are superseded as boundary evidence. `benchmark-v3.json` derives the near-boundary point from each request's position and timing bounds and also has zero objective and gradient differences for all four prefixes.

The scheduling change groups candidate rows by training-observation width, caps each kernel call at 1,024 rows, calls the unchanged `ds7_fast_baseline_adapter.fit_stationary_offsets` kernel, and restores each track's candidate order. Objective and gradient accumulation retains the frozen two-level reduction order: tracks first accumulate into their document, then document totals accumulate into the joint result.

This remains a prototype. It is not integrated into the executed Wave 4 arm or either frozen adapter.

## Optional fit-validation adapter

The separately named optional adapter delegates the existing fast `estimate` implementation and temporarily replaces only `ds7_baseline_adapter.JointObjective`. Component tests prove that the global is restored after success and after an injected exception, and that the optional ready arm's scientific config is exactly equal to the active fast arm's config.

The one predeclared, unscored first-eight fit completed in 144.97 adapter seconds under its 300-second cap. Its response is byte identical to the frozen first-eight response: east/north, all eight timing offsets, likelihood, RMS, convergence, boundary flags, `nfev=21`, and `total_nfev=63` all match exactly. External GNU `time -v` measured 145.98 seconds wall time and 639,140 KiB maximum RSS. The earlier frozen run recorded 170.30 adapter seconds; changing host load prevents assigning the entire observed ratio to batching.

This passes the declared optional computational adoption gate. It does not modify the frozen fast adapter, the baseline adapter, or an executed Wave 4 arm, and it adds no scientific or geographic evidence.

## Timing and memory

`benchmark-v2.json` compares the prototype to the **current fast per-track profiler**, not the older scalar profiler. Across the four points, summed current-fast time divided by summed batched time was:

| Frozen input | Current-fast / batched summed time |
|---|---:|
| prefix 1 | 1.218x |
| prefix 2 | 1.215x |
| prefix 4 | 1.495x |
| prefix 8 | 1.419x |

The median of the 16 individual ratios was 1.261x. One small prefix-1 out-of-domain call was slower at 0.924x; individual timings are noisy and no optimizer was run. The bounded v2 analyzer completed in 39.07 seconds with peak process RSS 896,556 KiB. The earlier v1 analyzer took 51.74 seconds, and the corrected-boundary v3 analyzer took 15.37 seconds. Cumulative benchmark time was 106.18 seconds, below the declared 180-second cap. V3 binds the current-fast comparator source hash and records the one-CPU, one-BLAS-thread, nice-19 policy in its receipt.

The RSS value includes sequential loading and evaluation of all four prefixes in one process and allocator retention. It is below 4 GiB, but it is not directly comparable to the earlier first-eight profile's 629,876 KiB. A controlled same-input peak-RSS and sealed end-to-end optimizer timing would still be required before adoption. This optimization addresses objective CPU cost; it does not solve full-88 document residency.

## Superseded first receipt

`benchmark-v1.json` is preserved. It compared against the frozen scalar profiler and flattened accumulation across documents, producing maximum differences of `1.6007106751203537e-10` in objective and `2.8421709430404007e-13` in gradient. It must not be used for the active-arm speed claim or exactness claim. The final prototype restores document reduction order, and v2/v3 use the current fast profiler as comparator. The v1 and v2 rows named `near_boundary` used +/-24.9 km and are now classified as out-of-domain probes; only v3 is boundary evidence for the active +/-12 km configuration.

## Component coverage

The component tests compare offsets and complete audit dictionaries against the frozen scalar oracle for:

- duplicate quantiles, including a constant row;
- deliberately multimodal stationary roots;
- grouping across repeated and distinct widths;
- splitting at a two-row cap and reassembling original track/candidate order.

Four component tests pass under the installed numerical runtime. Ruff reports no findings. No optimizer, score, pose, reference, raw IQ, RF collection, or source write was used.

## Artifacts and hashes

- Benchmark-v3 source snapshot: `executed-source-benchmark-v3.py`, SHA-256 `0fd98d1902e1db6b60477a6649112af605e99ae527572816c27ff8176be56903`
- Adapter-bound objective tool: `tools/ds7_batched_objective.py`, SHA-256 `2ef456b843b1f921877a1d8675dcb4b8e067074abda447d14cb00379f0be57dd`
- Optional adapter: `tools/ds7_batched_baseline_adapter.py`, SHA-256 `a967136e32d12b844cc5d206723198c1eb31eb230506df8c510110ef5aa90a33`
- Component tests: `tests/research/test_ds7_batched_objective.py`, SHA-256 `63b19982a22cc01c1e5d8be87129aaab4d5617461f00d4d207a1dc3fb94a1caa`
- Frozen cases: `cases-v1.json`, SHA-256 `7535162bb30eb0b14bbe42a8a46b634227771f79d954d3c1565a1d879bc9a5ce`
- Superseded benchmark: `benchmark-v1.json`, SHA-256 `2330f18f3bea9230e94b04d0d9e8602beb1d58b24efcd2b8556437228046bb26`
- Final benchmark: `benchmark-v2.json`, SHA-256 `3d103bffe3b14d4d4a1dd58802848414c416b013ca83b759c1fec2e39cc5a692`
- Corrected-boundary benchmark: `benchmark-v3.json`, SHA-256 `8f19b0662cf28650ebefe2facc3a26139e3f6f32292192b454ae1e20a4afcfe5`
- Fit-validation comparison: `fit-validation-comparison.json`
- Source performance profile README: SHA-256 `6975826a997f2c28970cb9aff6f85d331f4dd99e48eb419ce4872377ee17df74`
- Source performance receipt: SHA-256 `3307a5a3258d6ee5fdd334308090babf93e27bd75a6b29596d50094cfd1d378a`

The v2 and v3 receipts embed hashes for every request, response, and the executed tool. V3 additionally binds the current-fast comparator source.
