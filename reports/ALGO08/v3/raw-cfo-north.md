# North transfer of fixed-epoch CFO and the original named final fit

The combined candidate failed the North geographic transfer. Its containing error exceeded the released named v3 result by **254 m at fixed `c` and 393 m at fitted `c`**, both beyond the earlier +250 m limit. It also repeated the named false fix on the offer 100 m outside truth. This happened even though the new short-primary CFOs agreed much more closely with corresponding full-aperture measurements. [Frozen plan](raw-cfo-north-protocol.md) · [Sealed measurement](measurements/raw-cfo-north.json.gz)

| Original offer and result | Geographic decision | Position error, fixed / fitted `c` (m) | RF RMS, fixed / fitted `c` (Hz) | Owners per arm |
|---|---|---:|---:|---:|
| Containing, installed named | Fix | 105.690 / 140.779 | 5.406 / 5.167 | 302 |
| Containing, refined raw candidate | Fix | 359.810 / 533.409 | 75.601 / 77.297 | 265 |
| 100 m outside, installed named | False fix | 122.900 / 118.202 | 5.418 / 5.167 | 302 |
| 100 m outside, refined saved candidate | False fix | 359.868 / 533.419 | 75.601 / 77.297 | 265 |

Both current offers used the same 243 conditional and 22 predictive observations per arm, with the same ownership, order and roles. Of those 265 observations, 230 had changed receiver CFOs. The original named refit was paid and accepted in both offers. It used 0.105 CPU s on containing and 0.096 CPU s on the mirror. The later regional bound was not evaluated and isolated-family recovery made no attempt. Both regional scans stopped at `inside_score` after 25 probes. The existing curvature certificate correctly stayed inapplicable on the sealed packet because the maximum lane span was 296 s, above its 20 s threshold.

Truth is +100 m and −100 m inward from the respective nearby west faces. Candidate estimates lie 295.142 / 584.639 m inside the containing offer and 95.294 / 384.651 m inside the omitted offer in the solver's frame. The named estimates land on the face in all four fits. A rule that rejects only clamped endpoints would reject the valid named containing result and would keep the current false fix. The earlier unrefined mixed publication produced 390 / 121 m containing errors at 69.401 / 70.860 Hz RF RMS. The two historical combinations used different solver and publication settings, so that comparison cannot isolate the effect of refining CFO. [Archived mixed comparison](north-combined-protocol.md)

## Acquisition and timing

One acquisition verified the 19 original resident tmpfs members, 1,579,423,424 compressed bytes and 1,920,000,000 decoded bytes. All 1,200 signed stereo visits were admitted. The original schedule executed 304 full-aperture and 2,096 short-aperture antenna calls. The candidate retained the unrefined packet's exact 1,078 selected factors, with 82 from anchors and 996 from short primaries. It changed only signed CFO on 460 short factors, 230 per antenna, leaving anchor factors, membership, epochs, scores, flags and all 2,400 signed opportunities unchanged. The original named receiver selected 456 factors, whose lanes were all included in the candidate. For 396 short positives with a matched named counterpart, CFO error RMS fell from **10.602 to 1.806 Hz**, and 383 of 396 absolute errors improved. Fitting `c` made the final candidate RF RMS and horizontal error worse in each offer.

| Measurement boundary | CPU (s) | Elapsed (s) |
|---|---:|---:|
| Archived, same-fixture resident named raw containing process | 16.197 | 16.203 |
| Current refined raw containing process | 14.688 | 14.752 |
| Current containing authenticated acquisition | 8.540 | 8.543 |
| Current containing solve | 3.682 | 3.739 |
| Archived named mirror, solver only | 5.827 | 5.916 |
| Current mirror saved process | 6.088 | 6.109 |
| Current mirror solve | 3.313 | 3.326 |

The fixed-epoch refinement cost 0.900 CPU s within acquisition. The containing launch was about **1.10×** faster than the earlier resident launched v3 control on the same fixture and region. It was a noninterleaved historical comparison. The archived named mirror only measured its solver, so it compares to the current solver scope separately from through-exit time. Neither current child reported filesystem input blocks. The admitted waveform and index cache remained fully resident before and after the only raw run. No recording was copied, warmed, evicted or collected.

Both terminal publications completed and independently verified eight decoded PNGs. Containing and mirror used fully evaluated 144- and 137-node matched grids, respectively. Both grids and paths bind each run's actual verified position PNG. The mirror reused the refined packet byte-for-byte. No waveform reader or receiver executed on the saved path. The final native packet SHA-256 is `83d1c79b8acb8dc1d8720999af9791264558b2ac43505b6312e535fe832b91d0`; the detector recipe SHA-256 is `701c05ac380d8c1b4b528ddbfd6925d1c13dd9b1832dbe2959f52c3177065d66`.

The first preflight exposed a tuple requirement in the cache helper. The second reached the cache query and was denied for the non-owning account. Neither started a waveform process. The completed pair used the original staging owner's privileges, leaving file permissions unchanged. Timed source `eae9bfaea` and uncompressed result SHA-256 `22ea2a60534ebdd2e193c0577f9dc48cad26b882d2eda4c089b8f1b0d00f7ad1` bind the result. Run `raw_cfo_north_trial.py launch` under the recorded low-priority Gauss slot as the owner of the staged North recording, with a fresh tmpfs root, then `raw_cfo_north_score.py` after both clocks seal. Eight component tests passed across the new transfer and original signed finish suites.
