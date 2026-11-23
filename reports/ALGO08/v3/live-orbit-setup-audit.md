# Little repeated orbit setup on the live weak solver

On the genuine short-receiver DS30-0016 packet, new exact setup overlap accounts for an estimated **0.0641 CPU s**. The inclusive budget is **0.1521 CPU s**, which charges the entire cost of every propagation call with at least one newly reusable cell plus the repeated scalar parsing. Both are below the frozen 0.25 CPU s screen. The experiment ends at the weak saved solve. The size and timing of a dense overlap remain unmeasured. [Frozen protocol](live-orbit-setup-audit-protocol.md) · [Measurement](measurements/live-orbit-setup-audit.json)

## Charged work and exact repeats

| Original operation | Observed CPU | Exact repetition |
|---|---:|---|
| Nominal coarse and fine orbit matrices | 0.27119 s | 88,389 of 485,415 later cells, about 0.01954 s at per-cell cost |
| Regional proof orbit matrices | 0.03388 s | 54,930 cells already in nominal matrices, about 0.01366 s at per-cell cost |
| Previous-element matrices | 0.00062 s | 1,155 cells, including two wholly redundant calls that together cost 0.000305 s |
| Native snapshot validation | 0.08732 s | 22 distinct texts and 226,811 validated records, with zero repeated texts |
| Scalar element construction in phase forecast | 0.04424 s | 10,858 calls repeat within forecast and 9,776 first calls use lines parsed earlier in preparation |
| Scalar propagation in phase forecast | 0.01314 s | All 20,634 exact element-and-date requests distinct |

The early proof used the original full catalogue of 11,181 orbits, already handed off from preparation. Its 24 probes reproduced the original `eligible_exterior_separation` result and allowed the normal fit. Both proof propagation requests used overlapping nominal grid times. The previous dense proxy study already priced that cross-stage reuse, so its 0.01366 CPU s weak estimate stays outside the new budget. The relatively larger nominal overlap comes from its own coarse and fine grids. Slicing and assembling either orbit matrix would have an additional cost. [Prior dense proof study](proof-cold-reuse.md)

The live causal table already reused 21,412 canonical exports. It ran one phase-history preparation and one forecast, with two actual previous-catalogue parses. The scalar parser repeatedly constructs orbit objects from exact prior lines, but successive transitions propagate those elements to different Julian dates. Eliminating all 0.04424 s of scalar object construction would require safe reuse of the library objects across these dates. The observation does not establish that reuse, and the budget credits all of the construction CPU anyway. [Earlier causal-table study](../single-core-2x/solver-orbit-table.md)

## Saved numerical equivalence and scope

The sealed control is the candidate from the real cache-matched DS30-0016 pair. The harness verified the same signed native and terminal documents, original region and causal archive, installed graph asset, audited receiver recipe and complete solver bindings. Both calibrations retained the same 116 ordered owner/role rows. The position path, 179-node numerical grid and proof matched the archived publication, and both objective replay deltas were zero. [Cache-matched physical pair](weak-combined-raw.md)

| Calibration | Archived horizontal error | Saved RF RMS |
|---|---:|---:|
| `c = 0` | 1.31105 km | 121.52625 Hz |
| Fitted `c` | 1.69402 km | 120.29086 Hz |

The instrumented solve took 2.94769 CPU s, compared with the archived solve's 2.60528 CPU s. Both start at the saved detector handoff and include native graph preparation, early proof, inference and numerical evidence. The instrumented clock includes the trace callbacks and object retention. The subsequent bitwise intersection pass took an additional 0.04354 CPU s and is outside the solve clock. Neither measurement represents raw acquisition or filesystem publication. Two preliminary invocations reached the same saved route but stopped in the verifier due to Python coordinate tuples and integer receiver keys in the in-memory proof. The accepted comparison normalizes those representations to their canonical JSON equivalents.

The bulk trace covers the original `ecef_states` propagation port. It recognizes exact parse pairs captured in the live default-model parser and otherwise recognizes only the same retained satellite object. Thus it can miss independently constructed instances with unobserved provenance. It never treats a matching NORAD or epoch as element identity. All compared matching bulk keys returned bit-identical statuses, positions and velocities. The trace bills operations at their original call boundaries, so the cell-proportional estimate is a sensitivity rather than a measured cache gain. The inclusive budget is specific to the observed overlap and does not bound arbitrary SGP4 improvements.

The focused audit, existing catalogue handoff, and phase-state reuse tests passed together, 22 tests. To reproduce the accepted saved audit from the repository root, supply a fresh output path.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
flock -x -w 120 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 env \
  OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  timeout 30s "$release/venv/bin/python" -BPs \
  reports/ALGO08/v3/live_orbit_setup_audit.py /var/tmp/live-orbit-setup-audit.json
```
