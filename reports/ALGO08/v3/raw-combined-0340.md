# Combined receiver and curvature trial on DS30-0340

Both the combined candidate and installed ALGO08v3 acquired the original DS30-0340 recording and then failed at the same installed cavity-nomination check. Each exited with status 1. Neither published a fix or a withhold, so there is no calibration-arm error, RF RMS, terminal, numerical grid or PNG to compare. This trial measures time to error and retains both failures outside the completed-pair speed panel. [Frozen protocol](raw-combined-0340-protocol.md) · [Signed evidence receipt](measurements/raw-combined-0340.json.gz)

The frozen 455-member cohort has one member in the inclusive 512–767 issued-visit band. DS30-0340 issued 555 visits and admitted 388. Its two original upper-edge segments end in an incomplete capture, and both workers consumed the same 776 radio opportunities. The admitted recording was selected before opening prior outcomes or the geographic reference. The workers used the original 25 km offer, screen center and 46-snapshot causal archive. The candidate ran first with the original eight cumulative flags plus the curvature certificate and checked fixed-epoch CFO library. Its authentic saved packet binds detector recipe `701c05ac…65d66`. The named packet binds the installed receiver. [Cohort](../../2026_11_21_ds30_full/cohort.json) · [Fixed-epoch CFO rule](short-cfo-refine.md)

## What the failed runs established

| Observation | Combined candidate | Installed v3 |
|---|---:|---:|
| Signed factors across both radios | 218 | 194 |
| Signed factors on radio 0 / radio 1 | 85 / 133 | 75 / 119 |
| Largest winning-row lane span (s), saved recheck | 24.159669 | 21.975606 |
| Process start to sealed detections (elapsed s) | 3.222 | 5.028 |
| Process exit on error (elapsed s) | 6.784 | 8.690 |
| Process exit on error (CPU s) | 6.774 | 8.686 |

The saved recheck received only the two exact signed detection files. The time-only graph guard and curvature certificate were inconclusive on both. The named curvature shortcut requires a maximum lane span strictly below 20 seconds. The actual candidate stack reached the installed fallback, which reached `v5_core.infer` and raised during `nominate_families`. The failure occurred before the candidate could emit its usual post-publication refinement counters, so the 24-factor difference measures the receiver compositions and does not identify how many individual CFOs changed.

Both errors were `cavity nomination failed: ValueError('nonempty observation mask matching full design required')`. The pinned solver enters `nominate_families` only after constructing the signed base from the same scan, node and `c0` full design with a nonempty mask. The nomination copies that mask and clears the target family's slices, then constructs the identical full design again. The mask shape stays fixed, and the design length uses the same seed members and track values. The failure therefore comes from clearing every kept curved calibration row, which implies a single kept curved family at that point. The preserved evidence does not identify the family, its point count, or the terminal decision the solver would produce if it handled the empty exclusion. [Source trace and installed pins](raw_combined_band_score.py)

## Matched acquisition condition

The single read-only conditioning pass read 686,440,127 bytes across nine signed members. It took 8.624 s elapsed and 0.135 CPU s with 1,340,744 input blocks. All 167,593 payload pages were resident at the four before-and-after process checkpoints. The candidate had 2,984 process input blocks and installed v3 zero. Both reported zero major faults. The driver stopped on the first nonzero exit, then sealed the failed candidate before starting the still-pending named worker once with the same warm pages and staged inputs. Neither timed worker reran, and no second conditioning pass or other recording was opened.

The panel reader includes the canonical detector recipe, CFO artifact and receiver fingerprints in the implementation identity. It rejects old receiver configurations or either nonzero process exit. The failure receipt retains both clocks, packet identities, pinned sources, missing outputs and saved proof checks. Thirty scoped tests passed. The actual products are in `/dev/shm/leo-v3-raw-combined-0340-result01`, with candidate launch freeze `daba1e3a4` and the pending named launch in `34fce4288`. [Trial](raw_combined_band.py) · [Panel reader](same_build_raw_panel.py) · [Component tests](../../../tests/pipeline_eval/test_raw_combined_band.py)
