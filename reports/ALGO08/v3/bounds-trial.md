# Can three shortcuts halve ALGO08v3 runtime?

**The combination reproduced ALGO08v3's scientific outputs and took 155.54 s on dense DS30-0008. Installed ALGO08v3 took 149.89 s.** The half-time target for this pair was 74.94 s. The three shortcuts remove comparatively small portions of the pipeline, even on a recording with many opportunities to use them.

## The same recording through all eight figures

| One-core Gauss measurement | Installed ALGO08v3 | Combined prototype |
|---|---:|---:|
| Start through receiver detections, elapsed | 69.51 s | 79.92 s |
| Detections through numerical result, elapsed | 58.42 s | 54.25 s |
| Numerical result through publication and exit, elapsed | 21.95 s | 21.37 s |
| **Total elapsed** | **149.89 s** | **155.54 s** |
| **Total CPU** | **109.10 s** | **111.39 s** |
| Input pages resident before launch | 76.75% | 0.95% |

The prototype ran first. Both runs held the same exclusive benchmark slot on CPU 2, with nice 15, best-effort I/O priority 7 and one numerical thread. The operating system charged the prototype 4.26 times as many input blocks. This imbalance limits what the 5.65 s elapsed difference can tell us about algorithm cost. The lower solver-stage wall time is also a single observation. Both layout and association shortcuts were active, with 214 fixed layouts reused and 8,699 fine-recovery checks skipped.

Both builds published a fix. All 13,530 ordered receiver probes, 7,016 selections, satellite assignments, position paths, search grids and eight PNGs matched. The images matched both file bytes and decoded pixels. The derived receiver has its own build ID, which changes the detection and linked terminal file hashes. Installed ALGO08v3 also reproduced the archived recording result.

| Calibration applied to both builds | Horizontal error vs. DS30 operator site reference | Frequency-fit RMS |
|---|---:|---:|
| Fixed `c = 0` | 1.638978 km | 129.703040 Hz |
| Fitted `c` | 1.511956 km | 129.662931 Hz |

The site reference comes from the DS30 operator record. This recording has no independent GNSS survey. One full physical pair establishes reproducibility here. The off-site controls below test individual solver changes and do not measure full-pipeline fix rates at new sites.

## Where each shortcut saves work

| Change | Savings ceiling on saved inputs | What the prototype achieved |
|---|---|---|
| #1 Stop refining a losing timing and frequency hypothesis | On dense DS30-0008, a perfect ranking with free checks projects to 2.5 CPU s saved. The strongest practical bound examined projects to 1.19 s before paying for the check. | A cheaper bound saved 2.00% of native receiver CPU on weak DS26 lanes and 2.56% on dense DS30 lanes. All 138 ordered factors and the continuation decision matched. The stock rebuild reproduced the installed native library byte for byte. [Receiver measurements and compiler controls](https://github.com/misko/leo-tracker-reduxredux/blob/082e01b05bb8d57200fd989385868b0693b1e652/reports/ALGO08/v3/refine-bound.md) |
| #2 Reuse the fixed solver layout | On DS30-0008, repeat constructions accounted for 1.05 CPU s. Copies and checks reduce the attributable saving to about 0.77 s. On a southern simulation, repeat construction cost only 0.058 s. | Dense layout builds fell from 228 to 14. The solver still needed all 39,251 robust updates because position and weights couple the observations. Both calibration arms reproduced the dense and southern solver results. [Layout counts and timing](https://github.com/misko/leo-tracker-reduxredux/blob/082e01b05bb8d57200fd989385868b0693b1e652/reports/ALGO08/v3/incremental-layout.md) |
| #4 Rule out satellite associations across the offered region | Under the tested phase and orbit limits, 84.7–92.3% of whole-track candidates looked incompatible. V3 still uses some of those candidates to rank ambiguous matches, so this percentage cannot be claimed as removable work. | At a later stage with a hard cutoff, the guard safely skipped 8,699 of 40,189 dense recovery checks. Recovery took 0.118 s less on DS30-0008 and 0.269 s less on DS30-0374. Both calibration arms matched on five saved controls, including a northern missing-region case that again withheld. [Region assumptions, controls and costs](https://github.com/misko/leo-tracker-reduxredux/blob/082e01b05bb8d57200fd989385868b0693b1e652/reports/ALGO08/single-core-2x/regional-doppler-envelope.md) |

The prototype combines early receiver stopping, fixed-layout reuse and the hard cutoff in fine recovery. It uses the supplied region. Ground truth enters only when scoring a completed fix. The full physical comparison uses the same saved DS30-0008 recording, region and causal orbit archive for both runs. The independent-location checks above used saved solver inputs from simulations.

The single-core result supports closing this combination as a route to 2×. To halve the dense run, a successor needs to remove tens of seconds from work that still runs for every recording. Shared receiver scouting and the repeated robust position fits remain the larger targets. [Full comparison and reproduction command](https://github.com/misko/leo-tracker-reduxredux/blob/765cb77483f7677073302b08e48cabc037f4371d/reports/ALGO08/v3/bounds-physical-pair.md) · [Machine-readable paired timings and equality checks](https://github.com/misko/leo-tracker-reduxredux/blob/765cb77483f7677073302b08e48cabc037f4371d/reports/ALGO08/v3/measurements/bounds-DS30-0008-pair.json) · [Archived build inventory](https://github.com/misko/leo-tracker-reduxredux/blob/765cb77483f7677073302b08e48cabc037f4371d/reports/ALGO08/v3/measurements/bounds-DS30-0008-build.json)
