# Transfer of the combined DS30-0402 solver to public South

The combined solver published a valid fix for the containing South offer and a false fix for the nearby omitted offer. Installed named v3 made the same decisions. The isolated-family admission found no qualifying rescue in either run, and the endpoint repair never opened. This pair verifies that the combined publication runs on a separate site and preserves the named-v3 owners. The repair behavior remains untested here because its trigger never fired. [Frozen protocol](isolated-salvage-south-protocol.md) · [DS30-0402 development result](isolated-salvage-0402.md) · [Measured receipt](measurements/isolated-salvage-south.json.gz)

## Position and frequency

| Original South offer | Solver | Geographic decision | Error `c = 0` / fitted `c` (km) | RF RMS `c = 0` / fitted `c` (Hz) |
|---|---|---|---:|---:|
| +100 m east-face clearance | Named v3 | Fix | 0.816789 / 1.101409 | 6.502299 / 6.391940 |
| +100 m east-face clearance | Combined | Fix | 0.791086 / 1.085591 | 6.499045 / 6.390572 |
| −100 m east-face clearance | Named v3 | False fix | 0.817172 / 1.102143 | 6.502345 / 6.392003 |
| −100 m east-face clearance | Combined | False fix | 0.791086 / 1.085591 | 6.499045 / 6.390572 |

Fitting `c` reduced RF RMS by about 0.108 Hz in all four comparisons and moved the estimates about 0.28–0.29 km farther from the survey point. The 100 m omission made the published fix invalid even though its estimated position stayed close to the survey point. Both phase branches accepted the same signed age-squared correction. Each offer and each arm used 266 conditional observations and exactly matched the archived named-v3 observation-to-satellite digest. The regional probe examined 25 positions on each offer, stopped at `inside_score`, and did not withhold. The exterior gate did not evaluate a bound. The isolated hook reported `no_qualified_rescue_lost_at_seed` and ran zero paired repair fits on both offers. The ordinary repair and recovery routes also stayed inactive. The separate endpoint arithmetic cache was used in the normal solver, with six calculations on the containing offer and four on the omission. [Containing named-v3 control](../single-core-2x/measurements/exact-curved-lookahead-south-inside.json) · [Omitted named-v3 control](../single-core-2x/measurements/exact-curved-lookahead-south-offers.json)

## Cost and publication

| Original South offer | Combined solver CPU / elapsed (s) | Combined complete saved publication CPU / elapsed (s) | Combined child process CPU / elapsed (s) |
|---|---:|---:|---:|
| Containing | 3.181 / 3.181 | 5.127 / 5.129 | 5.343 / 5.345 |
| Nearby omitted | 3.215 / 3.216 | 5.200 / 5.202 | 5.459 / 5.462 |

The archived named-v3 omission solver took 4.487 CPU seconds and 4.549 elapsed seconds, about 1.40× and 1.41× the corresponding combined solver costs. The archived named-v3 containing process took 14.179 CPU seconds and 14.370 elapsed seconds and includes waveform acquisition. This table gives historical and current costs at their measured boundaries. Each combined child ran on CPU 2 with one numerical thread, `nice` 15 and I/O priority 7, and reported zero block inputs, outputs and major faults. No waveform or detector work ran, and no full raw-to-report speed was measured.

Both publications used a single authenticated handoff of the original 20 ms native packet over 1,200 issued and processed stereo windows and ran the installed exact Graph once. The original named controls and the two candidate workers share the signed native packet, raw authority, causal catalogue and cutoff. The scoring step reopened each terminal, its complete 137-node grid and position path, validated their link to the position figure, and decoded eight PNGs per offer. It read the original survey key after the two candidate clocks were sealed. The South offers are archived and geographically independent of DS30-0402. This is one known mirror pair with two offers over the same capture. [Transfer adapter](isolated_salvage_south.py) · [Component tests](../../../tests/pipeline_eval/test_isolated_salvage_south.py)

The transfer adapter and the original isolated-family and endpoint component suites passed 17 tests. The uncompressed receipt SHA-256 is `00a335f886c6139ab4951cf69b4fd4d829ba2eb9ab181ee07bfae2d48b422c4b`. The raw candidate publications are in `/dev/shm/leo-isolated-south-run01`.
