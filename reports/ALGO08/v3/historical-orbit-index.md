# Delay historical SGP4 construction until causal election

**Follow-up on the saved DS30-0016 comparison.** The original active publication preserved the terminal and figures but lost its early regional proof. The outer research observer captured intermediate text pairs before the original adapter converted them to SGP4 objects. Its runtime comparison does not establish a solver-equivalent cold-index speedup. The two-archive preparation assay remains valid at its measured preparation boundary. The corrected constructor now supplies native objects to both observers and passed the full North proof comparison. [Corrected North publication and diagnostic trace](north-orbit-index.md)

The fresh DS30-0016 preparation used **1.126 CPU s** with the index built by the earlier DS30-0008 scan, versus **1.768 CPU s** ordinary. It still verified all 99 archive reads and built its own elected orbit objects. On a separate complete saved DS30-0016 publication, the guarded index started empty and finished in **4.246 s elapsed**, versus **4.444 s** for the closest current-build ordinary fallback. The terminal, ordered owners, grid, path and eight PNGs matched. The warm transfer and cold publication measure different boundaries. [Protocol](historical-orbit-index-protocol.md) · [Preparation assay](measurements/historical-orbit-index-preparation.json.gz) · [Active saved publication](measurements/historical-orbit-index-active-0016.json.gz) · [Fallback publication](measurements/historical-orbit-index-fallback-0016.json.gz)

## Preparation on two signed archives

The index retains the original name, validated line pair, native NORAD and exact epoch in source order for each verified archive body. First use still pays the original native parser and SGP4 constructor for each new pair. On subsequent scans the ordinary archive reader authenticates each current body before lookup. The 48-hour and 72-hour elections use current collection stamps and cutoffs. The original coarse region screen still propagates the entire newest causal bank. After screening, the candidate creates orbit objects for the elected previous and genuine-previous rows and retained distinct phase epochs. Each scan has a fresh archive reader and its own runtime SGP4 objects. [Index and preparation assay](historical_orbit_index.py)

| Signed recording and scope | Preparation CPU / elapsed (s) | Newly indexed bodies / pairs | SGP4 objects created for elected scan rows |
|---|---:|---:|---:|
| DS30-0008 ordinary | 3.787 / 3.788 | None | 98,647 eager source objects |
| DS30-0008 cold index | 3.626 / 3.626 | 20 / 98,647 | 21,223 |
| DS30-0008 fresh scan, complete index | 3.184 / 3.184 | 0 / 0 | 21,223 |
| DS30-0016 ordinary | 1.768 / 1.769 | None | 92,697 eager source objects |
| DS30-0016 fresh scan, earlier DS30-0008 index | 1.126 / 1.127 | 1 / 3,574 | 20,105 |
| DS30-0016 fresh scan, complete index | 1.095 / 1.095 | 0 / 0 | 20,105 |
| DS30-0016 cold index, independent build | 1.581 / 1.581 | 20 / 92,697 | 20,105 |

The fresh scan saw 19 of its 20 bodies in the earlier capture. It paid for 3,574 new metadata objects and 20,105 elected objects, versus 92,697 eager source objects. Those counts cover source and selected-row materialization. Other SGP4 work in original validation and forecasting stayed active. The estimated retained immutable index was 64.5 MB after the dense archive, 66.9 MB after the weak transfer and 62.1 MB for a separate weak-only build. The candidate authenticated all 101 dense and 99 weak reads, covering approximately 181 and 177 MB of repeated reads respectively. Complete prepared tracks, noise, nominal and prior catalogues, provenance, history and forecast matched, as did the shape, dtype and bytes of every orbit-bank array. The assay ran once in the frozen order, with outer stage clocks and ordinary installed inner accounting. It used a single process across captures. Fresh-process loading and its costs remain unmeasured.

## Cold index in the saved positive-fix port

The installed regional-veto wrapper requires the concrete archive-reader type and captures the original causal catalogue. The opt-in preserves the reader instance and patches only its scoped `read` call to bind verified body text. It makes real elected SGP4 objects before the regional wrapper captures the catalogue. It also pins the installed exporter and checks the four angular domains that can raise on its native-object fields before any deferred export. An unsafe archive takes the original preparation path and receives its original errors or result. No such fallback occurred in the corrected publication. Keep this guard and content-authority verification for future variants. [Bound publication runner](historical_orbit_publication.py)

| Complete saved DS30-0016 boundary | Prior selective reference, CPU / elapsed (s) | Current-build ordinary fallback, CPU / elapsed (s) | Guarded cold index, CPU / elapsed (s) |
|---|---:|---:|---:|
| Whole process through exit | 5.383 / 5.386 | 4.439 / 4.444 | 4.239 / 4.246 |
| Decision and active publication | 4.249 / 4.250 | 3.284 / 3.287 | 3.086 / 3.086 |
| Inclusive numerical solve | 2.726 / 2.727 | 2.429 / 2.429 | 2.207 / 2.207 |

The active child spent **1.464 CPU s** on guarded preparation, including strict first construction for 92,697 metadata pairs, 20,105 elected runtime objects and all original reads. The cold path uses more total constructors than the ordinary source parser. The 0.20 s process difference includes the invalid early-regional path and cannot price the corrected cold path. The fallback and active children respectively incurred 336 and 1,376 input blocks and four and 13 major faults. The staged TLE and detection files remained in tmpfs. The already sealed child clocks exclude score verification. The first post-exit scoring check used a mismatched storage method. The corrected check isolated differences in the *terminal receipt* to ten named instrumentation clocks and verified both existing publication products. Comparison of the separate early-regional diagnostic was added in the North follow-up.

Both arms preserved **976 / 1,452 m** horizontal error and **116.340 / 115.526 Hz** RF RMS, with **116 ordered owners per arm**. Each child used one saved handoff. The signed detections, terminal, publication manifest and position path are byte-identical. The 179-node matched grid agrees except for its embedded elapsed duration. All eight encoded PNGs and decoded RGBA arrays match. No waveform was read in the assay or either publication. [Original selective accuracy](continued-cfo.md) · [Component tests](../../../tests/pipeline_eval/test_historical_orbit_index.py)

The two-archive assay ran on `d7aeca0ea` before the additional exporter guard. The active complete saved child ran on `ba323864f`. All paid numerical work used the single CPU 2 Gauss lock at nice 15 and best-effort I/O priority 7. The uncompressed preparation, active and fallback receipts are `3987ac56d2137af8e98d165b690773487c7873f5fe90e12685966324fd82b9cc`, `a679d9aeb5441c84db3c4977682ceb878570eec0941c81146b5144b9c46464fa` and `32fe762e202ff79622ea2bc71e8636d3e0bcedab9e79a031f39c65a7b8224e2d`.
