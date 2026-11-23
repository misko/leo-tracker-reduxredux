# One-pass history support on the named DS30-0160 inference

On saved DS30-0160, the named v3 inference recovered one unavailable earlier orbit inside its first fit. It published the **exact original named scientific result**, including both calibration arms and all eight PNGs. The one new saved diagnostic took **7.694 CPU s** in the named solve and **11.120 s elapsed** through process exit. The archived named run that repeated the full attempt took **12.565 solve CPU s** and **15.999 s elapsed**. The new process used the original signed factors, causal archive and offer already staged on tmpfs. [Frozen protocol](named-history-once-protocol.md) · [Sealed receipt](measurements/named-history-once-DS30-0160.json.gz)

| Scope | Archived named retry | One-pass named recovery |
|---|---:|---:|
| Named solve CPU | 12.565 s | 7.694 s |
| Whole worker CPU through exit | 15.994 s | 11.115 s |
| Whole worker elapsed through exit | 15.999 s | 11.120 s |
| Input blocks | 96 | 0 |

The archived control was a previous process. The two clocks use similar boundaries, with the new worker using the authenticated staged inventory and the original worker consulting original inventory metadata. The original clock did not instrument its failed preparation and inference separately. The observed solve difference was 4.871 CPU s. The new solve invoked preparation once for 2.029 CPU s and inference once for 5.564 CPU s. Inference included 0.299 CPU s for local confirmation and repair. No exterior score ran. No waveform data or new physical metadata was read.

## Exact result and failure scope

The adapter recognized the bare assertion at line 44 of the pinned installed `previous_bank` and independently reconfirmed failed earlier NORAD **58706** on the identical 0, 150 and 300 s alignment samples. The reported prior binds the original earlier element snapshot and its pre-cutoff epoch. The local retry excludes the failing earlier element using the named retry’s ordinary subset operation. It does not replace the current orbit. The original fit returned `stock` after that recovery, and the published terminal retained the original `history_support` provenance. Three focused controls exercised an ordinary no-retry call, selective causal recovery, and unrelated or unbound failure propagation. Nine tests passed with the saved boundary controls included. [Adapter](named_history_once.py) · [Driver](named_history_once_trial.py) · [Tests](../../../tests/pipeline_eval/test_named_history_once.py)

| Calibration | Position error from the original evaluation | RF RMS |
|---|---:|---:|
| Fixed `c = 0` | 0.798498 km | 126.335235 Hz |
| Fitted `c` | 1.089003 km | 126.092687 Hz |

The two publications matched the terminal and every reported arm value exactly. The verifier matched 1,037 ordered observation-owner-role rows per arm, the completed 179-point grid, optimizer path, all eight encoded PNGs and independently decoded RGBA bytes and sizes. The numerical sidecars each identify the actual published position PNG. The positions and RF residuals are the original named result. [Original evaluation and corrected cumulative result](prospective-0160-solver.md)

## Consequence for cumulative routing

The named-only guard fires when the first named attempt reaches its actual previous-bank assertion. It can recover before abandoning that attempt. It requires the actual selected rows and origin, so it neither predicts the case from receipt history nor avoids paid work before that assertion. A cumulative dispatcher could observe the same assertion and hand off the full signed packet to the trusted named solver, but it would also owe the failed cumulative prefix. The corrected cumulative receipt shows about **4.028 CPU s** in three disjoint abandoned scopes, including 0.495 s of regional work, 1.108 s of proposal work and 2.425 s of fallback inference. Any new combined route would have to count those costs and the named handoff. No earlier independent trigger was shown. The signed roster contains one `history_support` completion among 100 assignments and 92 completions. This diagnostic shows a correctness fallback on that case and no measured successor-wide saving.

The compressed result and launch binding expand to SHA-256 `a4f90d00c43a0076c30ffd3d12e51bce5943b079600f143808233f519e08f9fe` and `779bc83ef88c425d4ba593bb8f6752c6ef50c6cd32238639f932be55d1b6b85e`. [Launch binding](measurements/named-history-once-DS30-0160-binding.json.gz)
