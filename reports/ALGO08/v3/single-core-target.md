# Halving ALGO08v3 runtime on one core

Six follow-up experiments now have saved-component measurements, including a cold-read gain, two recovered solver failures and four approaches that missed their cost or accuracy targets. [Results and next experiments](first-experiments.md)

At naming, ALGO08v3 averaged 102.51 s elapsed across the first 55 assigned recordings. Its mean across the 52 successful fixes was 104.97 s elapsed and 77.74 s CPU. Even eliminating every second of waiting would still leave 25.25 CPU seconds to remove per successful fix. Eliminating publication alone would save 2.90 s. The two largest opportunities are reading and detecting signals, and solving the position.

| Successful fixes | Count | Mean elapsed, acquisition / solver / publication | Mean elapsed / CPU | Proposed stage budgets |
|---|---:|---:|---:|---:|
| All | 52 | 70.45 / 31.63 / 2.90 s | 104.97 / 77.74 s | 52.49 s total |
| Initially >95% of file pages in cache | 12 | 45.49 / 37.17 / 3.05 s | 85.72 / 83.54 s | 24 / 16 / 2.8 s |
| Initially <20% of file pages in cache | 31 | 79.45 / 30.57 / 2.86 s | 112.87 / 76.79 s | 34 / 19 / 3 s |
| DS30-0008, dense, warm | 1 | 52.70 / 56.98 / 3.34 s | 113.02 / 111.08 s | 29 / 24 / 3 s |

The two files that split the clock are the sealed native detections and the solver terminal. Acquisition includes launch, compressed reads, validation, both detector scans and writing the detections. Publication includes work through exit after the terminal appears. CPU is measured for each whole process. The warm and cold rows are observational groups, and nine successful runs fell in between. Cache state, scientific difficulty and scheduling can all change elapsed time. The budgets are engineering targets. [Per-recording clocks and cache residency](first-55/stage-clocks.csv)

### Three experiments

1. **Keep the acquisition busy while reducing detector work.** Separate time and bytes in verified reads, decompression and native DSP. In a cold successful run the median charged input was 8.25 GB. Reading that much in 34 s would require about 243 MB/s including concurrent detector work. Test one bounded next-member read/decode overlap against today's 16 MiB advisory hint. Preserve manifest order, all integrity checks, scan coverage and the single-core limit across workers. For DSP, a cheaper coarse search only earns a skipped exact score when a conservative bound proves it cannot affect the winner or continuation. Ambiguous and missing signals take the full two-scan path. Compare whole detection packets on saved weak and dense samples before a full run.
2. **Share orbit and likelihood work across the complete solve.** On DS30-0008 the solver alone takes 56.98 s, more than the 56.51 s budget for the entire run. Profile the frozen solver on the saved dense packet first. Try forming sparse per-family position and phase terms once and sharing them across discovery, recovery and held-family checks. Retain ambiguity checks, the supplied region and the two calibration arms. Compare returned positions, ownership and figure evidence. In parallel, cover the two observed orbit-interpolation exits with a regression fixture and verify recovery against the original ALGO08v2 fixes.
3. **Integrate only after the component savings add up.** Use saved DS30-0374 for an irregular scan, DS30-0008 and DS30-0402 for dense solves, and DS30-0316 for a short fix. Exercise independent northern and southern search regions, including a missing true region. Then time one alternating-order matched comparison at a time in the existing low-priority Gauss slot. Expand only when both timing gates and localization checks hold. Treat the two failure cases as regressions, never as successful early-return speedups.

The release test measures raw sealed I/Q through a terminal decision and the expected artifacts. The goal is candidate/v3 ≤0.50 both for the median per-recording elapsed ratio and for the ratio of summed elapsed. Report CPU, cache and run order alongside wall time. Report fix and withholding counts, errors on common fixes and all returned fixes, and frequency-fit changes separately for zero and fitted calibration. A faster fit on one roof leaves geographic generality open.
