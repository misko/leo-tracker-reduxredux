# Full-88 resource readiness from 24 real prepared captures

## Result

The bounded 24-document experiment completed successfully under a 4 GiB address-space limit. It loaded every currently frozen ready capture through the validated fast loader and made exactly one optional batched objective/gradient call at east/north zero and all timing offsets zero. No optimizer or scoring path ran.

The measured memory supports a future **separately authorized 8--10 GiB full-88 process envelope without adding streaming infrastructure solely for memory**. A full-88 objective call projects to about 18.5 seconds, and a 63-call fit projects to about 19.5 minutes before load, RMS, and optimizer overhead. The Wave 5 900-second budget is a panel lease, not the runner's full-88 ceiling. `ds7_eval` permits a separately declared one-unit lease up to 1,800 seconds. Under that ceiling, an 8 GiB bounded full-88 attempt is plausible if evaluation count remains near 63, all 88 inputs are ready, and immediate host checks pass.

## Measured 24-document footprint

| Measurement | Value |
|---|---:|
| Documents | 24 |
| Tracks | 1,439 |
| Candidate rows | 18,999 |
| Training observations | 39,038 |
| Retained NumPy array bytes | 1,642,625,856 bytes (1.530 GiB) |
| RSS before load | 76,652 KiB |
| RSS after load | 1,697,016 KiB |
| Peak RSS, external GNU time | 1,728,520 KiB (1.648 GiB) |
| Artifact hash validation | 1.995 s wall / 1.154 s CPU |
| Document load | 8.445 s wall / 8.280 s CPU |
| One objective/gradient | 5.056 s wall / 5.033 s CPU |
| Total internal | 15.506 s wall / 14.475 s CPU |
| Total external | 16.75 s wall |

The process validated all 72 observation/manifest/bank artifacts against their declared hashes. Their on-disk bytes total 1,479,584,719. The output objective and gradient norm were finite. The experiment stayed below 2 GiB RSS and far below its 4 GiB limit.

## Conservative full-88 extrapolation

The simple scale factor is `88 / 24 = 3.6667`.

| Quantity | Linear estimate for 88 |
|---|---:|
| Tracks | 5,276 |
| Candidate rows | 69,663 |
| Training observations | 143,139 |
| Retained NumPy arrays | 6,022,961,472 bytes (5.609 GiB) |
| Peak RSS, proportional from measured peak | 6,337,907 KiB (6.044 GiB) |
| RSS, fixed import baseline plus scaled load increment | 6,017,987 KiB (5.739 GiB) |
| One objective/gradient | 18.54 s |
| 42 objective calls | 778.6 s (13.0 min) |
| 63 objective calls | 1,167.9 s (19.5 min) |
| 95 objective calls | 1,761.1 s (29.4 min) |

An 8 GiB envelope leaves about 2 GiB above the proportional peak estimate; 10 GiB leaves about 4 GiB. That margin is credible for Python structures, optimizer state, and heterogeneous later captures, but it is not a guarantee. The remaining 64 captures can differ in track count, candidate count, observation width, and bank compression. Allocator high-water behavior and concurrent host pressure can also change RSS. Swap was already full and host load was elevated, so a future full-88 run should retain a hard memory limit and preflight available RAM immediately before launch.

The 63-call projection uses the completed first-eight fit's `total_nfev=63` only as a scale reference. Linear load time projects to another 31.0 seconds, while the final RMS pass and other overhead were not independently measured at 88 documents. This leaves roughly 600 seconds of an 1,800-second lease before unmeasured overhead if the fit remains near 63 calls. At 95 calls, objective time alone is about 1,761 seconds; projected load raises that to roughly 1,792 seconds before RMS or other overhead, so that path has no credible margin under the runner ceiling.

Neither 63 nor 95 calls guarantees convergence for a 90-parameter full-88 problem. Full-88 optimizer behavior may require a different number of evaluations, and per-call cost need not remain exactly linear. This measurement does not authorize changing starts, iteration limits, optimizer science, or running full88. It only shows that a future 8 GiB/1,800-second bounded attempt is a reasonable next resource experiment once all 88 inputs are frozen and host memory/load checks pass.

## Readiness decision

- **Memory:** ready for a separately declared 8--10 GiB experiment; the evidence does not justify building streaming infrastructure first.
- **Single objective:** ready; the 24-document call took 5.06 seconds and the full-88 planning estimate is 18.54 seconds.
- **Full fit resource plan:** a separately authorized 8 GiB/1,800-second attempt is plausible near 63 evaluations. A 95-evaluation path would exceed the practical budget after load and RMS overhead, and convergence is not established.
- **Scientific execution:** not performed. A future full-88 fit still requires its own frozen inputs, source hashes, runtime lease, hard memory enforcement, and unscored sealing before any evaluation.

## Provenance and exclusions

The machine-readable [receipt](receipt.json) binds:

- the 24-ready input contract, SHA-256 `5a2f8b03e8d24f4d7026fc5f8a806a0719c4036a7af9603293783b430dff351d`;
- the closed Wave 4 receipt, SHA-256 `43f7cb2ca992d09eccd0ffa0e680ca50b938ae12b184f1ee0706071ade61bc7c`;
- the optional arm and current fast-loader, batched-objective, baseline, and experiment-script bytes;
- declared and actual hashes plus byte counts for all 72 input artifacts.

The experiment used CPU/BLAS thread count one and nice 19. It did not read raw IQ, pose, reference, or scores; collect RF; export or mutate sources; run an optimizer; or launch full88.
