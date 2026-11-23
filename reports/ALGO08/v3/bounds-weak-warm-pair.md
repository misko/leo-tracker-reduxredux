# Warm ALGO08v3 bounds pair on DS30-0016

On one weak development recording, the original three-change bounds build took **26.068 s elapsed and 10.601 s CPU**. Installed ALGO08v3 took **38.383 s elapsed and 10.763 s CPU**. Both arms started with all signed input pages resident. The candidate gained 12.314 s overall, while the interval from the terminal file to process exit was 16.754 s shorter. Both arms used the same publication code and wrote identical PNG files. The elapsed ratio depends on this tail difference. The measured CPU saving was 0.162 s. [Pair receipt](measurements/bounds-DS30-0016-pair.json)

| Measurement | Installed ALGO08v3 | Bounds build |
|---|---:|---:|
| Launch to sealed detections | 5.936 s | 5.756 s |
| Detections to terminal | 4.442 s | 9.062 s |
| Terminal to exit | 28.005 s | 11.251 s |
| Total elapsed | 38.383 s | 26.068 s |
| CPU | 10.763 s | 10.601 s |
| Charged input blocks | 64 | 4,640 |
| Charged output blocks | 6,384 | 6,384 |
| Compressed pages resident at launch | 242,128 of 242,128 | 242,128 of 242,128 |

The measured ratios were **1.472× elapsed** and **1.015× CPU**. The candidate reused 64 fixed likelihood layouts. The hard fine-salvage guard evaluated 736 supports across 32 trajectories and rejected zero. This single warm measurement on DS30-0016 leaves the unequal input residency in the earlier DS30-0008 comparison unchanged. [Pair receipt](measurements/bounds-DS30-0016-pair.json) · [Dense pair and limitations](bounds-physical-pair.md)

## Scientific parity

Both runs reproduced all 1,426 ordered probes and 440 selections, the scan report, both fits and owner hashes, the scientific path and grid digests, and all eight PNG bytes and decoded RGBA hashes. The installed detection file matched the earlier weak stock control. The revised detector changed the native analysis digest and ID, and the resulting bindings in the terminal and publication documents. Their other fields matched. [Evidence and provenance checks](measurements/bounds-DS30-0016-pair.json)

The calibration arms kept observations, candidate support, priors and budgets matched. Both builds gave the same calibration effects against the radio/time-eligible operator site authority. [Calibration ablation](measurements/bounds-DS30-0016-pair.json) · [Reference audit](../../2026_11_21_ds30_full/reference-audit.json)

| Quantity | `c = 0` | Fitted `c` | Fitted minus zero |
|---|---:|---:|---:|
| RF RMS | 109.375120 Hz | 109.478940 Hz | +0.103820 Hz |
| Horizontal error | 1.643669 km | 1.661443 km | +0.017774 km |

## Inputs and reproduction

The driver matched the signed DS30-0016 recording and two segment manifests, 25 km offer, causal archive, and exact PGO receiver and both solver overlays from the original bounds experiment. Under one exclusive Gauss lock, the `leo` account ran the candidate first and installed ALGO08v3 second on CPU 2 at nice 15, best-effort I/O priority 7 and one numerical thread. A read-only pass over the 13 original compressed files warmed the candidate’s input outside the timing boundary. The installed arm’s input was already fully resident. The same Linux cache observer required all 242,128 pages immediately before each launch. [Build archive](measurements/bounds-DS30-0008-build.json) · [Input and launch receipts](measurements/bounds-DS30-0016-pair.json)

Use the [original Gauss invocation](bounds-physical-pair.md#reproduce-on-gauss) with this driver, a fresh output directory, and `--case DS30-0016 --first bounds`. The complete timed publication directories and raw pair receipt are under `/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-bounds-DS30-0016-warm-pair`. Thirty-four focused tests passed. [Driver](triage_bounds.py)
