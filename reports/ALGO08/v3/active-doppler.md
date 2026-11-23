# Causal Doppler competition did not improve dense short-lane purchases

At **240 paid short searches per rule**, the active selector recovered **83 of 226** held original owner lanes in either calibration arm. Uniform recovered **83**, and the previous recent-positive predicate with the same purchase budget recovered **92**. An oracle restricted to the same lane blocks could recover **169** owners, or **146** when it also had to pay for independent exploration. The measured orbital selector cost **10.895 CPU s**, against **0.460 s** of gross skipped receiver work. This screen did not advance to waveform or position replay. [Frozen protocol](active-doppler-protocol.md) · [Sealed plans and scored evidence](measurements/active-doppler.json.gz)

## What the selector knew

The first 1,024 admitted DS30-0008 stereo visits span 45.413 hardware seconds. The original target mask kept 258 full anchor antenna calls and 1,119 short base calls, and omitted 671 short calls. Exactly 386 of those omitted lanes had a genuine short detection and 226 had an owner in the completed original mixed-input result. The bound joins the same hardware-counter IDs and verified detector factor for both calibration arms. It samples 226 of the full record's 1,452 omitted owner lanes. The full record's historical schedule and owner counts are separate results. [Original mixed/alternating comparison](stereo-mask.md) · [Prior recent-positive scheduling](causal-mask-recovery.md)

The planner opened only the archived censored target packet and staged causal catalogue. It used the existing three-visit, two-RF folded-residual nomination to form possible satellite identities independently for either receiver. A block begins every four hardware seconds. Its inputs contain only earlier base-paid measurements within eight seconds of the block start. Bought-back outcomes and the current peer were unavailable to the selector. The target offer supplies geometry at the center and four corners. The selector uses two distinct causally nominated satellites above the horizon at the center, one admissible signed alias each, and compares their frequency intervals. Each interval includes the candidate's reanchored center-to-corner displacement and the greater of training RMS and 2,250 Hz. This approximates spatial uncertainty from five positions and a fitted receiver offset. The intervals do not certify the full region, oscillator drift or orbit uncertainty. [Original anchor-based orbital nomination](anchor-sky.md)

All three plans buy exactly three of every eight omitted antenna opportunities within the same exact radio/RF/edge stream. Active and recent-positive reserve one call for independent exploration. Both fill any remaining allowance at the last available slots. Uniform uses the same exploration slot plus two fixed spacings. Thirty-one tail opportunities lie outside complete blocks and remain in the omitted denominator. The saved signed metadata identifies block closure without a waveform read. This benchmark therefore prices a selector over archived recordings with available opportunity metadata. Its block closing rule would need the same admission information to enforce an exact budget during live capture.

## Equal-cost held results

| Policy | Direct trigger / reserve / forced buys | Positive / empty buys | Held owners recovered, either arm | Bought owners matched by a proposed NORAD and signed CFO |
|---|---:|---:|---:|---:|
| Doppler separation | 44 / 80 / 116 | 136 / 104 | 83 / 226 | 6 |
| Recent positive | 147 / 80 / 13 | 158 / 82 | 92 / 226 | 11 |
| Uniform | 240 fixed | 147 / 93 | 83 / 226 | 8 |
| Oracle with one fixed exploration call | 240 hindsight | — | At most 146 / 226 | — |
| Oracle with any three calls per block | 240 hindsight | — | At most 169 / 226 | — |

The existing 3/8 recent-positive study recovered 707 of 1,452 owners over the complete record with a cumulative quota and 1,625 buys. This trial applies the same last-paid-positive predicate at an identical blocked budget for all three policies. The orbital planner found two hypotheses on 621 of 671 omitted lanes. Their intervals separated on just 87 lanes, including 17 originally owned lanes. Across all 226 owned lanes, one of the two candidates supplied the correct archived NORAD for 33, and the correct NORAD and signed CFO within 4,550 Hz for 17. This diagnosis uses the archived owner only after all purchases were sealed. A retained detection can still contribute to a different successful solve. [Per-lane signed nominations](measurements/active-doppler.json.gz)

## Charged numerical work

| Measured stage | CPU / elapsed s |
|---|---:|
| Parse the causal catalogue | 1.9504 / 1.9507 |
| Catalogue screening and propagation | 0.0741 / 0.0773 |
| CFO projection at center plus four corners | 0.0358 / 0.0358 |
| Paid-history nomination, interval calculation and all schedule comparisons | 8.7913 / 8.7939 |
| Through the complete in-memory plan | 10.8951 / 10.9012 |

The projection shares time columns between radios. Thirty-three causal snapshots were used from the original 47 staged snapshots. The coarse horizon screen evaluated 122,947 satellite epochs. Fine propagation evaluated 55,648 epochs and retained 1,184 usable satellites. Five site projections produced 6,062,080 RF/time cells. A 5×5 lattice would produce about 30.31 million cells and costs **0.179 CPU s** by linear projection-only scaling, holding the same epoch geometry. Independently refitting histories at those sites would add work. The single-center nomination already inspected 1.72 million satellite/history cells over 24 cached receiver/block menus, with 26,048 admissible satellite/block fits before each shortlist. Nomination dominates the tested overhead.

The prior measured mean short call cost of 1.068 ms prices all 240 buys at 0.256 CPU s. The 431 remaining omissions save at most 0.460 CPU s at that mean, with the original decode, authentication, base calls and anchor charges intact. Even omitting the one-time catalogue load leaves the measured modeling cost well above the available receiver work. These clocks price an actual planning implementation on saved data, with receiver work stated as a projection. They supply no new raw acquisition or localization timing. [Original receiver cost](stereo-mask.md)

## Reproduce

Run `-m reports.ALGO08.v3.active_doppler plan NEW_TMPFS_DIRECTORY` under the exclusive Gauss CPU 2 slot with nice 15, I/O priority 7, one numerical thread and the checkout's `src` on `PYTHONPATH`. Then run `-m reports.ALGO08.v3.active_doppler score NEW_TMPFS_DIRECTORY`. The plan expands to SHA-256 `f4f9fc156660386861bb2683b2782b6a31743d24417dd1d56a17f31b6e397554`. The complete scored receipt expands to `ab3c6de05e2b0b6d355ee6230d77796167fd35f0409eacb7b1a159192cdbf184`. Three focused tests passed. [Runner](active_doppler.py)
