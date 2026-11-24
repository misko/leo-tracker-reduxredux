# ALGO08v3 successor validation on saved DS30 recordings

**The current candidate has yet to demonstrate a twofold end-to-end speedup with preserved accuracy on DS30 fixes.** It completed one whole physical withholding case 2.79× faster. Two physical fixes timed from saved detections gave substantially different results. The dense case improved both calibration arms. The held medium case lost 49 assigned observations per arm and increased fitted-calibration position error by 236 m.

| Recording | Timing boundary | ALGO08v3 → candidate, elapsed | Position result |
|---|---|---:|---|
| DS30-0107 | Complete original recording through process exit, one fresh run per arm | 1.417 → 0.508 s (2.79×) | Both withheld for insufficient curvature. Both calibration arms returned no position. [Paired result](adaptive-withhold-0107.md) |
| DS30-0160 | Same original 20 ms detection packet through exit | 15.999 → 14.353 s (1.115×) | Both fixed. Horizontal error increased from 798 to 822 m at fixed zero calibration and from 1,089 to 1,325 m with fitted calibration. [Held transfer](held-adaptive-0160.md) |
| DS30-0008 | Same hybrid detection packet through exit | 62.393 → 26.769 s (2.33×), or 31.090 s (2.01×) charging index construction | Both fixed. Horizontal error fell from 959 to 573 m and from 894 to 516 m. Only the first 192 of 6,772 visits used actual 8 ms substitutions. [Dense comparison](named-hybrid-baseline.md) |
| DS30-0016 | Complete historical v3 run compared with separately timed candidate acquisition and publication | 10.824 s measured → 7.511 s estimated (1.44×) | Historical v3 and current saved candidate both fixed. Horizontal error fell from 1,644 to 490 m and from 1,661 to 980 m. Candidate RF RMS rose in both arms. [Weak comparison](weak-all8-adaptive.md) |

The last three rows cannot supply a cohort runtime or fix-rate estimate for a new end-to-end release. In particular, charging the index construction to the dense case addresses one cost. It still leaves original waveform processing outside both saved clocks. The candidate used an adaptive grid and all eight figures were verified on each saved positive. On DS30-0160 the omitted grid locations have no same-fit full-grid reference. The physical DS30 cases also share a site.

## Keeping ALGO08v3's original position solution

The next solver experiment kept the original satellite selection, repairs, fits, and standard figures and reused repeated computations. All three physical recordings returned exactly the original ordered satellite assignments, both calibration endpoints and RF residuals, the 179-location grid, the path and all eight PNGs. Each comparison starts with the same original signed 20 ms detections. The named comparison clocks are historical. [First two recordings](exact-named-route.md) · [Dense transfer](exact-named-dense.md)

| Recording | Named v3 elapsed | Exact solver elapsed | Speedup | Horizontal error for both methods, fixed / fitted |
|---|---:|---:|---:|---:|
| DS30-0160 | 15.999 s | 10.330 s | 1.55× | 798 / 1,089 m |
| DS30-0316 | 18.358 s | 16.887 s | 1.09× | 1,945 / 1,863 m |
| DS30-0374 | 28.324 s | 23.630 s | 1.20× | 1,855 / 1,935 m |

On the first recording the saved speedup was **1.55×**. Across the first two, total time fell **34.357 → 27.217 s** (**1.26×**), with **1.28×** by the median paired ratio. Adding the prospectively selected 6,770-visit DS30-0374 brought the totals to **62.681 → 50.847 s** (**1.23×**), with **1.20×** by the median paired ratio. Both solvers fixed 3/3. DS30-0160 avoided repeating a fit after recovering a missing prior orbit. DS30-0316 took the ordinary inference path and had no such retry. These cases differ in how much work the solver can reuse.

The candidate launches could use the same prebuilt orbit index. Its signed digest and producer match the independently timed **4.320 s** build. Charging that build once across the three completed runs gives **55.168 s**, or **1.14×** versus named v3. DS30-0316 also incurred a 1.127 s rejected startup before its legacy manifest path convention was corrected. Including both that startup and the index gives **56.295 s**, or **1.11×**. The candidate reused four indexed catalogue bodies on DS30-0160 and zero on DS30-0316. [Index build clock](weak-all8-adaptive.md) · [Per-case activation](exact-named-route.md)

On **DS30-0016**, both solvers consumed the complete signed detections from the candidate's 20/8 ms receiver. The exact solver took **6.453 s** against **6.918 s** for the named solver on that same packet, a **1.07×** saved speedup. Both produced identical 490 m and 980 m errors, retained all 115 assigned observations per arm, and reproduced the full grid, path and eight PNGs. The original v3 receiver on the same recording had produced 1,644 m and 1,661 m errors. This comparison tests the handoff from the shorter receiver to the exact solver. Its 6.453 s clock starts after the detections already exist. [Weak receiver-to-solver comparison](named-weak-all8.md)

The first 1,024 visits of DS30-0008 supplied a separate shorter-duration test for the earlier combined solver. Both workers used the same 45.379 s physical observation span. Saved publication took 11.513 versus 9.316 s (1.24×). Both produced eight PNGs, but both position errors were about 7.7 km and the candidate increased error by about 8 m. An earlier candidate attempt failed to complete its final source receipt. These successful-run times illustrate the cost of publishing a fix from that short span. [Prefix result and both attempts](resident-positive-pair.md)

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

The receiver experiment reduced the number of pilot samples converted and preserved every ordered detection on two physical members. Complete acquisition CPU showed mixed results across repeated runs, so this change does not advance. A paired launch from identical original samples through verified publication and exit is still needed for a physical fix. The latest opportunity to copy the rest of DS30-0016 expired under storage load after zero new archive reads. [Receiver measurements](verifier-pilot-support.md) · [Staging receipt](guarded-cfo-0016-idle-a16.md)

## The receiver budget on the three matched exact fixes

These recordings also have independent v3 clocks from original waveforms. For each row, subtract that recording's observed saved-solver improvement from its historical time between sealed detections and exit. The difference between half its original end-to-end clock and this estimated downstream time is the receiver's budget. This calculation transfers the time saved on the same input. It avoids charging the saved worker's separate launch twice. Raw and saved launches took place at different times, so the result is an experiment target.

| Recording | Original raw v3 time | Original acquisition | Saved solver improvement | Acquisition budget for 2× | Required compressed MB/s |
|---|---:|---:|---:|---:|---:|
| DS30-0160 | 33.93 s | 19.28 s | 5.67 s | 7.99 s | 575 |
| DS30-0316 | 40.37 s | 23.10 s | 1.47 s | 4.39 s | 853 |
| DS30-0374 | 84.85 s | 56.16 s | 4.69 s | 18.43 s | 456 |

The original stage-clock cohort supplies all three denominators. DS30-0160 and DS30-0316 were fully resident at launch. DS30-0374 was 10.6% resident. A separate 164.40 s historical v3 run also exists for DS30-0374. Using that slower wall clock as the denominator would make the acquisition budget look much larger. [Stage-clock inventory](measurements/acquisition-throughput.json) · [Separate dense run](exact-named-dense.md)

On two original DS30-0008 members, the faster of two acquisition passes that **only decoded and verified** bytes processed 567 MB per CPU-second. As a sensitivity calculation, give all three recordings that rate, zero I/O waits and zero time for signal detection. The resulting candidate/v3 elapsed ratios are **0.503 median and 0.492 summed** against a 0.500 target on both gates. Throughput can vary by recording and implementation. The measured cost makes a change to how data are read and verified worth testing alongside faster signal processing. Run `PYTHONPATH=.:src python reports/ALGO08/v3/adaptive_receiver_budget.py --exact-cases` to reproduce the table and both ratios. [Original two-member measurements](physical-stage-envelope.md)

## Reading the same original signal with less decoding

Two saved DS30 members now have an independently verified experimental representation that separates each 20 ms capture into an 8 ms prefix and a 12 ms tail. The receiver authenticates every encoded block and decodes the samples its 20/8 ms detector uses. Corrupting an unused tail caused verification to fail on both recordings. The resulting detection packets matched the ordinary 20/8 ms receiver byte for byte. The installed 20 ms receiver reads the same physical opportunities but can select different factors. [Protocol, fault injection and timings](seekable-eight-raw.md)

| Acquisition elapsed for one 64-visit physical member | DS30-0008 | DS30-0169 |
|---|---:|---:|
| Original v3, 20 ms | 488 ms | 435–448 ms |
| Ordinary archive, 20/8 ms | 349 ms | 338–362 ms |
| Verified split archive, 20/8 ms | 207 ms | 193–204 ms |
| Building and independently verifying the split archive from the original | 492 ms | 432 ms |

With the split archive already built, acquisition was **2.36×** faster on DS30-0008 and roughly **2.1–2.3×** on DS30-0169 against the original 20 ms receiver. These clocks end at acquisition, before final detection selection and position solving. For the first analysis of each existing recording, adding conversion and readback gives about **699 ms** and **625–635 ms**. Both exceed the ordinary v3 acquisition cost. A prospective format needs a measured writer-to-first-analysis comparison to establish its cost for a new scan. The full-file reader experiment on the existing format saved up to 19.5% CPU on DS30-0169 but failed to give a repeatable improvement on DS30-0008. [Original-format receiver](sealed-stream.md)

## One process from original I/Q through the position and figures

The common research entry point now runs the 20/8 ms receiver and the exact named solver in one process using the supplied search region. On the 1,200-visit North geographic simulation, v3 and the candidate processed all 2,400 opportunities, published both calibration arms and verified all eight PNGs. The new candidate took **15.561 s**, compared with **19.967 s** for the fresh instrumented v3 baseline (**1.28×**). Acquisition fell from 9.507 to 6.144 s, with another 0.071 s for the candidate's end-of-recording detector selection. Solving fell from 7.172 to 6.082 s. Rendering took 1.698 and 1.649 s respectively. [Raw launch, timing boundaries and receipts](exact-named-raw.md)

Horizontal error changed from **106 to 112 m** at fixed zero calibration and **141 to 128 m** with fitted calibration. RF residual RMS increased from 9.7 to 45.0 Hz and from 18.6 to 50.4 Hz. The two receivers selected different observations. An exact solver on identical input can therefore preserve the solver result while the complete pipelines produce different positions. Reusing the candidate's detections with the published far-outside offer produced a withhold with no PNGs. North is a previously evaluated simulation and the omission was a saved-detector check.

On the complete physical DS30-0107 original input, the same entry point withheld for insufficient curvature in **0.577 s**. Its position and RF fields were null in both arms. This verifies the physical withholding path. The physical DS30 positive-fix gate remains open.
