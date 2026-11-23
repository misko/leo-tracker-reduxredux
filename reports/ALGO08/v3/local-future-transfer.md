# Protected Doppler-track repair on a second physical DS30 recording

The repair recovered useful evidence on physical DS30-0016 and the public northern and southern simulations. It failed both prespecified position screens on DS30-0057. All 1,220 forward assignments retained their satellite and role, but the 138 additions shifted horizontal error from **378 to 708 m** with fixed-zero calibration and from **641 to 937 m** with fitted calibration. Installed v3 gave **426 and 525 m**. Preserving assignments solved a northern track reconstruction problem. It could not ensure that appended measurements improved the fix on a second recording from the same roof. [Frozen DS30-0057 protocol](local-future-0057-protocol.md) · [First three containing offers](local-future-repair.md)

![Change in horizontal error from installed ALGO08v3 across four saved containing offers](development/local-future-transfer.png)

## Saved publication results on DS30-0057

| Input and solver | Error, fixed / fitted (m) | RF RMS, fixed / fitted (Hz) | Numerical solve CPU (s) | Saved packet through exit, elapsed / CPU (s) |
|---|---:|---:|---:|---:|
| Original v3 detections, installed solver | 426 / 525 | 109.97 / 109.83 | 9.909 | 13.548 / 13.545 |
| Short detections, forward-only compact solver | 378 / 641 | 120.22 / 120.25 | 6.206 | 10.682 / 9.881 |
| Same short detections, protected repair | 708 / 937 | 121.28 / 121.31 | 6.503 | 10.106 / 10.103 |

Stock reproduced the original terminal digest and all eight archived PNG byte and pixel hashes. All three fresh runs returned two positions, completed the 179-point grid, and wrote eight verifiable PNGs. Each process used one low-priority Gauss core and a fresh tmpfs output directory with a shared warm font cache. The single execution order was forward, stock, repair. The repaired saved publication took 74.6% of stock elapsed. Raw reading, decompression, authentication and detection are outside these measurements. The forward arm had about 0.80 s more elapsed than CPU, so the lower repaired elapsed does not establish a cheaper repair. The repair actually used 0.222 s more process CPU. [Fresh receipts and phase clocks](measurements/local-future-0057.json.gz) · [Replay and independent scorer](local_future_0057.py)

Each calibration comparison within a build used the same observations, region, candidates and search budget. Fitting calibration increased repaired position error by 229 m and RF RMS by 0.025 Hz. The older unfiltered candidate on the same original short detections gave **240 / 297 m** with RF RMS **125.30 / 125.31 Hz**. Its lower position error despite greater RF residual illustrates why waveform fit and localization have to be assessed separately. [Prior matched raw result](short-raw-diagnostic.md)

## Which observations were added?

Of 225 future-supported opportunities, the repair admitted 138 observations across 12 satellites. It rejected ambiguous nominations and applied both calibration arms' existing alias, visibility, pointwise and whole-track checks. Forward and reverse selection cost 0.092 CPU s, nomination 0.049 s and refit 0.092 s. The accepted additions included 74 conditional and 64 predictive observations per arm.

| Comparison with the original full-aperture receiver and installed-v3 owners | Existing 1,220 | Added 138 |
|---|---:|---:|
| A full-receiver factor was present on the same lane and visit | 1,219 (99.9%) | 83 (60.1%) |
| Both receivers selected a rank-zero factor within two wrapped samples and 250 Hz | 1,150 (94.3%) | 45 (32.6%) |
| Stock fit assigned the same satellite | 1,141 (93.5%) | 47 (34.1%) |
| Stock fit assigned a different satellite | 41 | 26 |
| Stock fit left the observation unassigned | 38 | 65 |

Both calibration arms yielded the same witness counts. The counterfactual receiver and stock assignments were examined after the candidate published. The two receivers observe the same waveform. Stock disagreement identifies where the evidence is weaker, but cannot label individual measurements as erroneous or prove which observations caused the error. [Witness census](measurements/local-future-0057-witness.json) · [Probe join and census](local_future_witness.py)

The prespecified confirmation follow-up retained 59 additions on DS30-0057 and reduced errors to **440 / 703 m**, within the 250 m development screen. On DS30-0016 it retained only four of the nine additions and gave **1,730 / 2,019 m**. Its fitted arm exceeded stock by 358 m. Those results use archived full-aperture counterparts. The estimated cost of reproducing their target and continuation history was 1.09 CPU s on DS30-0016 and 4.68 s on DS30-0057 before rereads. [Confirmation test and work accounting](full-confirmed-future.md)

**A single global damping fraction for the position update cannot rescue these two physical recordings.** Suppose the output moves a fraction of the shortest geographic path from the forward position toward the repaired position. On DS30-0016, the fitted arm must move at least 0.631 km to have any chance of reaching the stock-plus-250 m error limit. The entire update is 1.052 km, which requires a fraction of at least **0.600**. On DS30-0057, the repaired position exceeds the corresponding limit by 0.162 km and the update is only 0.378 km. The fraction must be at most **0.570**. These two necessary bounds follow from the triangle inequality and are disjoint even before considering fixed-zero calibration. This calculation applies to blending the two published positions along their connecting path. Refitting with per-observation reliability can move in other directions. [Reproducible bounds](local_future_transfer_figure.py)

## Implications for halving time

On the mirrored public location tests, the repaired solver also returned false fixes for **both** offers that omitted the correct location by 100 m. Both 52.5 km omissions withheld before fitting, with null positions and zero figures. Both containing offers reproduced the earlier repaired outputs. The new evidence therefore preserves the far-omission behavior and leaves the near-edge ambiguity unresolved. [Matched containing and missing-region publications](local-future-omissions.md)

An opt-in research launcher now runs the same selection and solver policy on original and saved short inputs. The 18-visit DS30-0227 warm raw smoke took 1.354 s for installed stock versus 1.348 s for the candidate through exit on tmpfs. Both withheld and the candidate's saved replay reproduced its live detector and terminal exactly. This single small withhold verifies the entry point. [Raw and saved smoke](local-future-cli.md)

The physical errors rule this candidate out for a larger DS30 timing panel. The two numerical shortcuts studied alongside it also have bounded scope. In the saved dense cold search, competing assignments reused 86–92% of normalized rows for unweighted statistics, yet none of the final robust weights matched across the three leading assignments. Even granting the entire cold, salvage and post-salvage predictive stages for free leaves 17.35 s of dense solver CPU, above the modeled 16 s target. In the receiver, every audited installed-v3 candidate reaching the final fractional verifier passed the gate (80 dense and 58 weak), as did all 34 audited short weak candidates. A perfect early-rejection oracle on those confirmed lanes would skip zero work. The dense short rejection rate remains unmeasured. [Solver census](dense-assignment-reuse.md) · [Receiver ceiling](fractional-reject-ceiling.md)

On the existing dense DS30-0008 timing reference, a complete saved publication reduced solver CPU from **26.105 s** with the unfiltered short input to **21.781 s** with protected selection. Fixed-zero and fitted error were **2.298 / 2.238 km**, respectively, versus **1.639 / 1.512 km** for installed v3. The full-aperture confirmation variant stopped before this case. The updated models give median / summed elapsed ratios of **0.802 / 0.783** on the first four and **0.751 / 0.750** on the first sixteen at the recorded whole-file acquisition rate. At the faster prefix rate those ratios are still **0.556 / 0.530** and **0.522 / 0.528**. Both ratios must reach 0.500. The model now requires at least **276 MB/s** effective acquisition on the first four with this solver. No new four- or sixteen-recording raw evaluation was run. [Dense scientific and timing comparison](dense-protected-cost.md)

To reproduce the timed version, use commit `55908f440` and run `local_future_0057.py trial FRESH_TMPFS_ROOT` using the release interpreter, research modules, Gauss lock and single-core settings in the original raw diagnostic. Run `local_future_0057.py score FRESH_TMPFS_ROOT` in that checkout's scoring environment. The later `local_future_witness.py FRESH_TMPFS_ROOT` reads the sealed products. The figure script reads the two checked-in compressed receipts. [Detection sources](measurements/short-raw-diagnostic.json) · [Figure script](local_future_transfer_figure.py)
