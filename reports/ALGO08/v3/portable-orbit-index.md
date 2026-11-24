# Portable TLE record metadata across fresh processes

The corrected guarded DS30-0016 comparison takes **4.369 s ordinary and 4.187 s indexed** through saved publication. The two paths preserve all 24 projection evaluations and the original regional evidence. A separate geographic omission check reproduces the same false fix on both repaired paths. [Corrected physical comparisons](portable-omitted-region.md)

**The initial DS30-0016 publication timings are withdrawn.** The portable and scan-local pilot adapters passed TLE line tuples to the early regional scorer where it expected Satrec objects. They returned the same terminal and figures while omitting the paid regional diagnostic. The standalone preparation measurements below remain valid within their measured scope. The repaired DS30-0316 study verifies both exact preparation and the original regional calculation through a saved publication. [Corrected medium publication](portable-orbit-0316.md)

A fresh DS30-0016 process reused **212,721 records from 19 of 20 causal TLE bodies** with the **2,688,577-byte** DS30-0008 artifact. The remaining body used the original cold source-index logic. All 223,913 records still went through the strict installed parser with no fallback. The fresh process read and verified all 99 original body requests and reproduced the full prepared arrays, history and provenance exactly. Ordinary preparation took **1.615 CPU s**, compared with **1.351 CPU s** for the disk-backed index plus **1.487 ms** for artifact read and verification and **0.305 ms** for compatibility checks. [Frozen protocol](portable-orbit-index-protocol.md) · [Sealed evidence](measurements/portable-orbit-index.json.gz)

| Isolated saved preparation | Prep CPU, s | Original archive verification CPU, ms | Strict parser CPU, ms | Sidecar export or load CPU, ms | Through-exit CPU / elapsed, s | Peak RSS, KiB |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0008 ordinary | 3.742 | 89.5 | 85.1 | — | 4.461 / 4.462 | 420,980 |
| DS30-0008 indexed + export | 3.572 | 73.4 | 87.5 | 15.0 | 4.319 / 4.320 | 328,336 |
| DS30-0016 ordinary | 1.615 | 97.7 | 83.5 | — | 2.156 / 2.158 | 389,640 |
| DS30-0016 fresh portable index | 1.351 | 94.3 | 86.4 | 1.5 | 1.978 / 1.980 | 312,584 |

The ordinary control uses the released CausalPreparationParser, strict native batch parser, causal export cache and deferred GC. Archive verification and strict parsing are included in preparation. The through-exit clocks also include a fresh interpreter, release and signed-input checks, preparation fingerprinting, reporting and exit. All four measured workers charged zero input blocks and zero major faults. Dense preparation opened 101 authenticated archive references containing 223,923 parsed records. Weak attachment of the cached primitives took 83.6 CPU ms inside preparation. The immutable artifact plus its parsed offsets retained 2,693,414 bytes in the weak process. The source index still retains the original names and lines for same-scan reuse, estimated at 62.12 MB after weak preparation. [Adapter](portable_orbit_index.py) · [Fresh process runner](portable_orbit_index_trial.py)

Each entry is an unsigned native NORAD and signed UTC epoch nanoseconds in strict source-record order. The index binds ordered record counts, original authenticated body SHA-256, SGP4 2.27 and its binary, the exporter, strict parser, epoch conversion and implementation. Opening it requires a separately trusted index SHA-256. The ordinary reader verifies original bytes on every physical body request. The strict parser supplies names and line pairs afresh for each new body, and parsed IDs must match the cached order. Cold bodies or incompatible index files take their original guarded paths. Elected orbits are always materialized from authentic lines. The caller has to trust the source-index producer associated with the verified artifact digest.

The initial saved selective DS30-0016 publication activated the portable index and matched both same-input controls for terminal, ordered 116 owners and roles per arm, path, scientific 179-point grid and all eight encoded and decoded PNGs. Its early diagnostic returned `every item must be a Satrec`. The ordinary control evaluated the original probes. Position errors versus the operator site authority were **0.976164 and 1.451671 km** for fixed zero and fitted calibration, with RF RMS **116.340 and 115.526 Hz** respectively. There was one genuine saved handoff and zero waveform access.

| Same selective publication, DS30-0016 | Solve CPU, s | Publication CPU, s | Through-exit CPU / elapsed, s | Input blocks / major faults |
|---|---:|---:|---:|---:|
| Ordinary same-input publication | 2.726 | 4.249 | 5.383 / 5.386 | 0 / 0 |
| Earlier cold source index, regional diagnostic errored | 2.207 | 3.086 | 4.239 / 4.246 | 1,376 / 13 |
| Earlier portable index, regional diagnostic errored | 2.028 | 2.882 | 4.003 / 4.008 | 520 / 10 |

The application continued after the regional diagnostic exception, so successful exit and a matching terminal did not establish equal work. The original offline scorer verified terminal and media while missing this diagnostic. The outcome above preserves the individual clocks for audit. An earlier dense export stopped after 4.352 CPU s before writing because archive source digests use bare hex. That attempt did not produce a portable artifact and is retained separately. Five component tests passed. [Cold source-index evidence](historical-orbit-index.md) · [Tests](../../../tests/pipeline_eval/test_portable_orbit_index.py)

Run `portable_orbit_index_trial.py NEW_TMPFS_PATH --prepare` in the isolated pinned release interpreter through the single shared low-priority Gauss slot. Use the sealed `portable_sha256` with `portable_orbit_index_trial.py NEW_PUBLICATION_PATH --publish-from PREPARATION_PATH --pin SHA256`. The guarded adapter also accepts a fresh `PortableSourceIndex` via its `index_factory` argument for a separately bound saved input.
