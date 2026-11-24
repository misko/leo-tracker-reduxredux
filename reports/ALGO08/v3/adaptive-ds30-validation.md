# ALGO08v3 successor validation on saved DS30 recordings

**The current candidate has yet to demonstrate a twofold end-to-end speedup with preserved accuracy on DS30 fixes.** It completed one whole physical withholding case 2.79× faster. Two physical fixes timed from saved detections gave substantially different results. The dense case improved both calibration arms. The held medium case lost 49 assigned observations per arm and increased fitted-calibration position error by 236 m.

| Recording | Timing boundary | ALGO08v3 → candidate, elapsed | Position result |
|---|---|---:|---|
| DS30-0107 | Complete original recording through process exit, one fresh run per arm | 1.417 → 0.508 s (2.79×) | Both withheld for insufficient curvature. Both calibration arms returned no position. [Paired result](adaptive-withhold-0107.md) |
| DS30-0160 | Same original 20 ms detection packet through exit | 15.999 → 14.353 s (1.115×) | Both fixed. Horizontal error increased from 798 to 822 m at fixed zero calibration and from 1,089 to 1,325 m with fitted calibration. [Held transfer](held-adaptive-0160.md) |
| DS30-0008 | Same hybrid detection packet through exit | 62.393 → 26.769 s (2.33×), or 31.090 s (2.01×) charging index construction | Both fixed. Horizontal error fell from 959 to 573 m and from 894 to 516 m. Only the first 192 of 6,772 visits used actual 8 ms substitutions. [Dense comparison](named-hybrid-baseline.md) |
| DS30-0016 | Complete historical v3 run compared with separately timed candidate acquisition and publication | 10.824 s measured → 7.511 s estimated (1.44×) | Historical v3 and current saved candidate both fixed. Horizontal error fell from 1,644 to 490 m and from 1,661 to 980 m. Candidate RF RMS rose in both arms. [Weak comparison](weak-all8-adaptive.md) |

The last three rows cannot supply a cohort runtime or fix-rate estimate for a new end-to-end release. In particular, charging the index construction to the dense case addresses one cost. It still leaves original waveform processing outside both saved clocks. The candidate used an adaptive grid and all eight figures were verified on each saved positive. On DS30-0160 the omitted grid locations have no same-fit full-grid reference. The physical DS30 cases also share a site.

## How much faster must acquisition become?

The table gives the **minimum uniform effective compressed MB/s** from launch until sealed detections that would satisfy both existing time gates. A run passes those gates when both the median paired candidate/v3 elapsed ratio and the ratio of summed elapsed times are at most 0.5. Higher required rates leave less time to read, authenticate, decode and detect the same recordings.

| Assumed speedup from detections through exit | First 4 DS30 | First 16 DS30 | Historical 55 DS30 |
|---|---:|---:|---:|
| Unchanged downstream time | 752 | 651 | 486 |
| 1.115× on every fix, as in the held medium saved comparison | 574 | 501 | 399 |
| 2.007× on every fix, as in the dense saved comparison charging the index build | 299 | 264 | 235 |
| 2.331× on every fix, as in the dense saved comparison with an index available | 270 | 244 | 219 |

These are sensitivity calculations using the enrolled v3 recordings and elapsed stage clocks. Each row applies one assumed speedup uniformly to all measured post-detection time, including publication and exit. A saved-process clock contains its own startup work, so its ratio is only an assumption about how the corresponding raw stage might scale. Recordings without stage splits retain their original total elapsed. Each panel uses its original membership, including failures. No receiver was benchmarked at the rates in the table. Earlier cold two-member acquisitions reached 225 and 248 MB/s on short prefixes. Sustained throughput over complete fixes remains an open measurement. [Original rosters and acquisition measurements](panel-tail-ceiling.md)

Run `PYTHONPATH=.:src python reports/ALGO08/v3/adaptive_receiver_budget.py` from the repository root. The output gives each timing gate separately. The calculation verifies the hashes of both saved comparisons, the enrolled subsets and the historical stage data. [Calculation](adaptive_receiver_budget.py)

The held case changes the next experiment. Reuse computation while keeping the original satellite assignments and both fitted endpoints, then compare on a second packet before expanding the roster. The receiver experiment checks how much work can be removed from processing the same pilot samples while preserving ordered detections. The first qualification that can establish a speedup on a physical fix remains a paired launch from identical original samples through verified publication and exit.
