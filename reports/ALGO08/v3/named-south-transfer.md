# Original signed finish on the South near-edge offers

The current named-survivor finish reproduced installed v3's two endpoints and RF residuals exactly on each original South offer. It published the containing fix and repeated the false fix when truth was 100 m outside. Both calibration arms kept the same 266 conditional owners on both offers. Their observation-to-satellite digests match the installed named controls, and their exact owner order and roles match the previous warm finish. [Frozen protocol](named-south-transfer-protocol.md) · [Previous warm and named comparison](isolated-salvage-south.md)

| Offer and method | Geographic outcome | Horizontal error, fixed / fitted `c` (m) | RF RMS, fixed / fitted `c` (Hz) |
|---|---|---:|---:|
| Containing, current and named v3 | Fix | 816.789 / 1,101.409 | 6.502299 / 6.391940 |
| Containing, previous warm | Fix | 791.086 / 1,085.591 | 6.499045 / 6.390572 |
| Omitted, current and named v3 | False fix | 817.172 / 1,102.143 | 6.502345 / 6.392003 |
| Omitted, previous warm | False fix | 791.086 / 1,085.591 | 6.499045 / 6.390572 |

Fitting `c` reduced the current RF RMS by about 0.110 Hz while increasing horizontal error by 285 m on each offer. Compared with the warm finish, the named finish increased error by 25.7 / 15.8 m on the containing offer and 26.1 / 16.6 m on the omission. The signed final pairs passed their ordinary acceptance check. The isolated-family option found no qualifying rescue, and no endpoint repair or inference fallback ran. Both regional proofs stopped at `inside_score` after 25 probes. The later exterior test did not evaluate a bound.

## Offered-face geometry

The figures below use the solver's east–north frame. A positive clearance is inward. The east face is the closest face to truth and every reported endpoint.

| Offer | Truth (m) | Current and named fixed / fitted (m) | Warm fixed / fitted (m) |
|---|---:|---:|---:|
| Containing | +100.000 | +442.797 / +382.913 | +449.316 / +385.527 |
| Omitted | −100.000 | +242.474 / +182.783 | +249.316 / +185.527 |

The false-fix endpoints are 242.5 and 182.8 m inside the east face, with inward errors relative to truth of 342.5 and 282.8 m along its normal. A check that only rejects an exterior or boundary-clamped endpoint accepts both offers. A fixed minimum inward depth in **(242.474, 382.913] m** separates these particular offers under both arms in hindsight. The two fitted locations move only **0.656 / 0.805 m** across offers. The apparent separation comes from the 200 m translation of the face over one waveform, with a common position bias. This does not validate a generic depth cutoff. A transferable rule needs independently tested evidence of exterior support or a calibrated boundary uncertainty measure, with genuinely containing near-edge counterexamples. The earlier all-channel bilateral score already flagged this southern omission in an offline diagnostic, while the installed terminal decision remained a false fix. [Regional evidence](geographic-rf-fold.md)

## Runtime and artifacts

| Offer | Current solve CPU / elapsed (s) | Current saved process CPU / elapsed (s) | Previous warm saved process CPU / elapsed (s) |
|---|---:|---:|---:|
| Containing | 3.333 / 3.335 | 5.511 / 5.517 | 5.343 / 5.345 |
| Omitted | 3.289 / 3.290 | 5.360 / 5.363 | 5.459 / 5.462 |

The named refit cost 0.081 and 0.082 CPU s. The current saved-worker internal through-publication CPU / elapsed was 5.259 / 5.264 s and 5.186 / 5.188 s, narrower than fresh child launch through exit. Historical warm solve CPU was 3.181 and 3.215 s. Archived installed-v3 containing time, 14.179 CPU / 14.370 elapsed s, includes waveform acquisition. Its omitted case reports solver-only time, 4.487 CPU / 4.549 elapsed s. These measurements cover distinct scopes. The current pair is two saved processes on one original acquisition, with the same pinned offer and archive, no waveform or original manifest access. It does not measure a raw speedup.

Each current fix published the complete 137-node grid, both calibration paths and eight verified PNG files. Each position sidecar matched its own published position PNG digest. The matched one-pass render performed four native orbit plots, two native residual plots, one position plot and one track RMS plot per offer. All eight PNGs changed in bytes and decoded pixels relative to the warm finish on each offer. Both runs executed one exact Graph. The original 1,200 stereo visits were all admitted. The signed original causal cutoff and installed named detector identity were preserved.

Both timed workers used the standard saved CLI with `--named-survivor-finish --direct-orbit-figures --direct-residual-figures`. The [sealed receipt](measurements/named-south-transfer.json.gz) has uncompressed SHA-256 `7653b038a30e723e46bf3a5cb690ce8a52d841378f5d60964e1708e2d51cdcca`. Run `named_south_transfer.py launch` from `ffec3bcca` under the recorded Gauss slot using the already staged inputs and a fresh tmpfs root. Run `named_south_transfer_score.py` on that output after both clocks are sealed. Thirteen tests passed across the saved South, previous warm, mixed-finish and named-survivor component suites.
