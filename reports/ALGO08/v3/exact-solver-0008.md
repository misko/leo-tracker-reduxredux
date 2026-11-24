# Exact solver transfer on the complete dense DS30-0008 packet

The corrected solver completed the full unfiltered mixed 20/12 ms DS30-0008 publication in **26.921 CPU seconds and 26.947 elapsed seconds**, compared with **27.027 CPU seconds and 27.036 elapsed seconds** for the archived same-packet exact Graph and grid control. Numerical CPU fell by **0.294 s**. The 89 ms through-exit difference across separate launches gives no reliable process-level speedup. Both calibration outcomes and every scientific and media artifact matched. [Frozen protocol](exact-solver-0008-protocol.md) · [Signed comparison](measurements/exact-solver-0008.json.gz) · [Historic control](cumulative-grid-projection.md)

| Same saved packet | Prior exact Graph and grid | Grouped rank and duplicate check |
|---|---:|---:|
| Numerical solve CPU / elapsed | 22.868 / 22.875 s | 22.574 / 22.579 s |
| Render and encode CPU | 2.349 s | 2.490 s |
| Complete publication CPU | 26.785 s | 26.601 s |
| Through-exit CPU / elapsed | 27.027 / 27.036 s | 26.921 / 26.947 s |
| Process input blocks / major faults | 0 / 0 | 3,992 / 47 |

The stable Graph check removed **9 duplicate proposals in 16 lane finalizations**, costing 0.612 ms CPU, and preserved 90,746 ordered edges, 208 tracks and 6,461 assigned points. The grouped rank activated once. All **1,792** curve calls used the exact compact path with zero full fallback. The certificate omitted **2,515,096 of 2,644,992** original row profiles. The original-shape bias multiplication still processed 115,623,936 cells. Inclusive rank took **4.046 CPU s**, with a further **58.3 ms** for the seven-node receipt. All seven nodes matched the independently sealed same-packet rank digest exactly. That earlier isolated pair measured 4.303 → 3.919 CPU s, with its own timing scope. [Prior rank evidence](catalogue-block-bound.md) · [Actual work counters](measurements/exact-solver-0008.json.gz)

Ordinary causal catalogue preparation took **2.661 CPU s** including 101 authenticated archive reads and 20 strict body parses. The existing DS30-0008 portable artifact uses this same recording and cutoff. The other documented DS30-0306 producer has a later cutoff. The run loaded neither of those artifacts. All 47 original archived snapshots were already staged in tmpfs, with 20,539 resident pages and 84,051,499 logical bytes. Both projection sources and the checked native library were verified before launch. The run made zero waveform calls and no backing archive access. The process-wide fault and block counters do not identify their files. [Input custodians and pins](measurements/exact-solver-0008.json.gz)

The held selector chose the original unfiltered packet. Both saved runs used 6,772 issued visits, 6,765 admitted, seven exclusions, 13,530 signed probes and **7,336 factors**. The original offer and cutoff produced the same `inside_score` regional result, with all 25 probes and five selected source digests. Both arms kept all **4,367 ordered owners and roles**. The terminal, complete 179-point matched grid, optimizer path and all eight encoded PNGs and decoded pixels were identical. Both sidecars bind their own verified position PNG. [Original held choice](held-anchor-route-publication.md) · [Publication evidence](measurements/exact-solver-0008.json.gz)

| Calibration | Historical named v3 error | Same-packet control and candidate error | Named v3 RF RMS | Same-packet control and candidate RF RMS |
|---|---:|---:|---:|---:|
| `c = 0` | 1,638.978 m | 919.007 m | 129.703040 Hz | 140.961400 Hz |
| fitted `c` | 1,511.956 m | 857.413 m | 129.662931 Hz | 140.949802 Hz |

Named v3 used genuine full-aperture detections. The mixed inputs differ from that named comparison. The solver-option comparison keeps both calibrations on the same mixed inputs and reproduces both the named region and the historical mixed results. [Named raw comparison](dense-full-short-raw.md) · [Sealed reference and RF scoring](measurements/exact-solver-0008.json.gz)

## Full-recording budget

Half of the resident named-v3 qualification's **113.021 s** is **56.51 s**. With the measured **26.947 s** saved process charged in full, at most **29.564 s** remains for reading, verification and unthinned native detection over the 8,182 MB original. That requires at least **277 MB/s** through the whole verified acquisition. The historical unthinned mixed acquisition used **32.403 CPU s and 60.449 elapsed seconds** from a mostly nonresident start. Adding its CPU to this saved process CPU gives an optimistic **59.324 s** before any input wait, about **2.81 s** above the target. Adding the two observed elapsed components gives **87.396 s**, about **1.29×** versus the resident named clock. These are conditional component sums. Separate-process setup and saved handoff work may overlap or disappear in a combined entry. Cache, dependency demand and storage wait may move elapsed in the other direction. No new detector-to-exit measurement was made. [Matched named clocks](measurements/dense-control-clocks.json) · [Original mixed stage clock](measurements/dense-measured-budget.json)

One fresh candidate ran under the shared Gauss CPU 2 lock at nice 15, best-effort I/O 7 and one numerical thread. The candidate exited zero before the verifier opened the scoring authority. Ten component and adjacent tests passed. The uncompressed receipt SHA-256 is `f4750387b41c8247e6195a162a5653f11c2fd2281b23faa857cddbb1bc29255a`. [Runner](exact_solver_0008.py) · [Tests](../../../tests/pipeline_eval/test_exact_solver_0008.py)

Use the archived release interpreter and the same locked environment as the medium transfer. Run `exact_solver_0008.py preflight` to check the staged packet, archive and source pins. Run `launch FRESH_TMPFS_PATH` for the timed child, then `verify FRESH_TMPFS_PATH` with repository `src` ahead of the released `src` for read-only verification. [Environment](exact-solver-0057.md)
