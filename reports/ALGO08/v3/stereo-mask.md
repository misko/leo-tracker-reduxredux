# Moderate short-lane thinning loses the dense position fix's accuracy

Skipping one antenna on selected short visits kept both full anchors and at least one genuine observation opportunity per visit. The larger schedule avoided **4,435 of 11,834** dense short searches, worth **4.735 CPU s** at the recorded mean. Both masks failed the predeclared 250 m position screen on dense DS30-0008. Weak DS30-0016 and the southern simulation passed both containing tests. No mask qualified for the displaced South follow-up. [Frozen rules](stereo-mask-protocol.md) · [Numerical scores and costs](measurements/stereo-mask-summary.json) · [Sealed publications and bindings](measurements/stereo-mask-publications.json.gz)

## Both calibration arms

Each projected packet uses actual unfiltered 20/12 ms observations on retained lanes. The scheduler sees only the admitted sequence, exact RF, channel and pilot edge. It preserves the original clocks, exclusions, raw inventory, causal cutoff and region. There is no search outcome, alternative location, stock output or owner ID in the selector. The installed graph was rebuilt, and the same full-catalogue checked solver fit both calibration arms on the selected evidence. Each of the six containing runs completed with verified grid, objective path and all eight PNGs. The dense and weak runs had 179 grid points, and South had 137 and 151. No solver fallback ran. [Earlier 37.5% stereo-visit drop at older 20 ms factors](mixed-aperture-crossed.md) · [Chronological stop failures](late-prefix-stop.md)

| Containing offer | Named v3 error km, zero / fitted | Full mixed error km, zero / fitted | Quarter mask error km, zero / fitted | Target mask error km, zero / fitted | Passes both controls |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense DS30-0008 | 1.639 / 1.512 | 0.919 / 0.857 | 1.698 / 1.638 | 2.213 / 2.077 | Neither |
| Weak DS30-0016 | 1.644 / 1.661 | 1.311 / 1.694 | 1.223 / 1.280 | 1.198 / 1.243 | Both |
| South simulation | 0.817 / 1.101 | 0.454 / 0.515 | 0.478 / 0.418 | 0.698 / 0.589 | Both |

The quarter mask worsened dense error by **0.779 / 0.780 km** versus the full mixed input, even though it met the allowance versus named v3. The target mask regressed against both controls. Its fixed-zero Southern result came within 6 m of failing against the full mixed control. Weak errors improved on both masks, but their fitted endpoints shifted by about 0.91 km from the full mixed solution. Similar error magnitude can conceal a different solution.

| Containing offer | Full mixed RF RMS Hz, zero / fitted | Quarter RF RMS Hz, zero / fitted | Target RF RMS Hz, zero / fitted | Owners per arm, full / quarter / target |
| --- | ---: | ---: | ---: | ---: |
| Dense DS30-0008 | 140.961 / 140.950 | 138.105 / 138.078 | 138.989 / 138.932 | 4,367 / 3,313 / 2,814 |
| Weak DS30-0016 | 121.526 / 120.291 | 109.807 / 109.612 | 112.729 / 112.581 | 116 / 97 / 86 |
| South simulation | 8.312 / 8.188 | 8.974 / 8.392 | 12.648 / 10.588 | 468 / 366 / 335 |

Dense calibration endpoints were only **79 m** apart on the quarter mask and **143 m** apart on the target. Both estimates stayed more than 4.6 km inside the offered region. In-sample RF RMS fell with the altered support while the horizontal errors increased. The two masks moved the same-calibration dense endpoints by 592 m and 531 m. Another full fit to check that instability would already spend most of the original solve. Dense lost 973 or 1,452 original owners directly to omitted factors, plus 336 or 355 despite those observations still being measured. Among shared owners, 13 or 330 changed satellites and 55 or 63 changed roles. Shared owners kept their satellites on weak and South. Weak also kept every shared role. [Owner overlap and endpoints](measurements/stereo-mask-summary.json)

## What a receiver could actually save

The dense recording paid 1,696 full calls consuming 4.716 CPU s, 11,834 short calls consuming 12.635 CPU s, and 15.053 CPU s in the other authenticated acquisition work. The quarter and target schedules preserve all full calls. Pricing an omitted short call at the whole-recording measured mean grants exact opportunity counts with an estimated per-lane cost. It does not supply actual native costs by slot. Both masks keep all source decode and verification charged. The projected direct CPU delta adds the difference in measured saved solver CPU and charges the saved planner and history audit, 42–45 ms dense. This projection excludes raw I/O timing, figures, imports and process exit. [Original acquisition receipt](measurements/dense-full-short-raw.json.gz) · [Roster gate](roster-savings.md)

| Offer and mask | Omitted short calls | Factors retained / full | Estimated native CPU saved, s | Saved solve CPU, s | Saved launch through exit, elapsed s | Projected direct CPU saved, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense quarter | 2,956 | 5,740 / 7,336 | 3.156 | 22.557 | 27.080 | 6.662 |
| Dense target | 4,435 | 4,922 / 7,336 | 4.735 | 24.618 | 29.622 | 6.177 |
| Weak quarter | 308 | 382 / 475 | 0.319 | 2.514 | 5.394 | 0.392 |
| Weak target | 463 | 330 / 475 | 0.480 | 2.474 | 5.354 | 0.593 |
| South quarter | 520 | 541 / 703 | 0.519 | 3.963 | 7.300 | 0.892 |
| South target | 784 | 459 / 703 | 0.782 | 3.881 | 7.211 | 1.238 |

The dense target clears the **4.616 s** first-four native budget screen by 0.119 s gross, and the quarter clears only the **2.735 s** first-sixteen screen at the native boundary. Neither is scientifically eligible. The best-case observation-preserving dense oracle can skip **5,454 empty short lanes**, worth **5.823 s** at the same mean. Meeting 4.616 s would require identifying 4,324 of those empties, **79.3%**, if the screen were free and always kept positive lanes. Their emptiness is visible only in the already paid reference measurements. The fixed schedules skipped 1,596 and 2,414 genuine factors. They provide no evidence for an online rule with that oracle accuracy or cost. [Previous quiet-visit counterexample](quiet-cycle.md)

An eventual gated receiver would have to account for unmeasured history donors. The original unfiltered recipe makes its factor choice independently within each paid lane. The saved replay keeps no unseen continuation decisions. Under the existing 12-opportunity, eight-second history horizon, **5,499 / 4,818** retained dense positive lanes had an earlier lost positive donor on the quarter / target masks. A solver or selection rule that depends on the original continuation would have to rebuild that history from paid measurements.

Recovering all skipped dense work after a speculative solve requires at least **2.365 / 3.548 GB** of retained omitted-lane I/Q, or an authenticated revisit. Both masks touch **106 of 106** signed members. A revisit using the released boundary returns to **8.182 GB compressed, 18.30 MB of index rows and 10.835 GB decoded** before any additional fit. Paying each skipped call exactly once and fitting complete evidence puts a failed attempt at least **22.599 / 24.663 CPU s** above the original acquisition-and-solve path even with saved I/Q and free storage. The existing regional and solver checks accepted the dense outputs, so this experiment supplies no reliable trigger to pay that recovery selectively. [Original member roster](measurements/late-prefix-stop.json.gz) · [Member closure and retry arithmetic](measurements/stereo-mask-summary.json)

## Reproduction

The shared schedule and detector-recipe binding are frozen at `e4b2fb2ec`. The saved protocol and driver were frozen at `bea54b1d9`. An initial dense launch stopped before timing because its acquisition document and later terminal use different work IDs. Commit `1a1e489ff` resolves the single addressed acquisition artifact and leaves its SHA, mask, and model unchanged. All six solves were on saved signed inputs, with zero waveform calls, fresh tmpfs output directories and the shared low-priority Gauss CPU 2 lock. Five owned tests passed. Use `stereo_mask_trial.py run CASE OUT` with the installed payload, release package and research directories on the saved solver's `PYTHONPATH`. Use `stereo_mask_score.py ROOT SUMMARY` with the repository source and scorer on `PYTHONPATH` after all terminals seal. [Saved runner](stereo_mask_trial.py) · [Scorer](stereo_mask_score.py) · [Tests](../../../tests/pipeline_eval/test_stereo_lane_schedule.py)

The complete receipt expands to SHA-256 `c6a973403103206290fbd5cb9bb904533d0919ac40810ccddc19482eac0e5795`. The scored summary hashes to `9f7a4245d566e558eb7fd4732f284537d31c65df2a67c03266b603fb0d0c7026`.

For a separately authorized public North raw wiring check, the same target predicate on the archived original mixed packet projects 304 full calls, 1,312 paid short calls and 713 factors. The canonical detector recipe, emitted probe array and analysis identity SHA-256 values are pinned in the offline receipt. This comparison fixture supplies no additional saved position and was outside the three-case selection panel. [Offline North cross-check](measurements/stereo-mask-north-offline.json)
