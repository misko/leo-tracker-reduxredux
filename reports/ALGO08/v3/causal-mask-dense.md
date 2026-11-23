# Causal lane recovery improves the dense mask and still loses to the complete receiver

The exploratory dense replay restored the exact **1,625** searches chosen by the frozen recent-positive 3/8 rule. Horizontal error improved from **2.213 / 2.077 km** on the target mask to **1.584 / 1.549 km** with fixed-zero / fitted calibration. That met the allowance against named v3 and missed it against the full mixed receiver by 665 / 691 m. The solver also spent 6.379 more CPU seconds than the full mixed control, exceeding the **2.992 s** estimated receiver saving. The one fresh saved publication completed in **36.954 s elapsed**. [Exploratory protocol](causal-mask-dense-protocol.md) · [Original coverage result](causal-mask-recovery.md) · [Sealed dense publication and post-run score](measurements/causal-mask-dense.json.gz)

## Signed evidence and positions

The original coverage study had no qualifying rule and stopped before a fit. This separate test used its already sealed recent-positive row after observing 707 matching original owners versus 530 with equal-cost uniform recovery. It made no change to the rule, history or purchase quota. The 1,625 true short searches added 1,112 original positive factors and accounted for 513 empty outcomes. The 6,034-factor candidate used no survey coordinates, owner IDs or subsequent waveform information to choose additions. It retained every base-paid factor byte, full anchor, original radio probe, clock and causal inventory. [Sealed purchase list](measurements/causal-mask-recovery-plans.json.gz) · [Hindsight comparison](target-owner-recovery.md)

| Detector evidence on DS30-0008 | Horizontal error km, zero / fitted | RF RMS Hz, zero / fitted | Owners per arm | Saved numerical CPU, s |
| --- | ---: | ---: | ---: | ---: |
| Named v3 | 1.639 / 1.512 | 129.703 / 129.663 | — | — |
| Full mixed 20/12 ms | 0.919 / 0.857 | 140.961 / 140.950 | 4,367 | 26.105 |
| Alternating target | 2.213 / 2.077 | 138.989 / 138.932 | 2,814 | 24.618 |
| Target plus causal recent-positive purchases | **1.584 / 1.549** | 141.946 / 141.757 | 3,279 | 32.484 |
| Target plus all omitted original owner lanes, hindsight | 0.704 / 0.661 | 143.620 / 143.496 | 4,426 | 24.173 |

Both arms published a valid fix on the original containing offer with a complete 179-node grid and all eight verified PNGs. Each numerical sidecar bound its own position image. The normal regional proof continued after 25 probes. No solver fallback was taken. This single fit improved error over the target mask by 628 / 528 m and remained 881 / 888 m behind hindsight. Compared with the target, RF RMS increased despite the improved position. The two acceptance controls and the audited reference were opened for scoring after the candidate process and terminal sealed. [Target and full baseline evidence](stereo-mask.md)

| Prior publication | Shared original IDs | Original IDs missing | New IDs | Shared NORAD changes | Shared role changes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full mixed | 3,145 | 1,222 | 134 | 344 | 31 |
| Alternating target | 2,478 | 336 | 801 | 519 | 11 |
| Hindsight reopening | 3,159 | 1,267 | 120 | 353 | 29 |

These comparisons had the same counts in both calibration arms. The new solution selected **638** purchased observations as owners. Of 707 buys originally owned by the full mixed solver, **619** were still owned and **550** retained their original satellite. Owner recall before fitting therefore overstated survival under the new graph and association.

## Actual saved solve and estimated receiver work

The fresh saved process used **36.947 CPU s and 36.954 elapsed s** through exit, with zero input/output blocks and zero major faults. Mask assembly and source validation took another 0.693 CPU s once, outside that process. The previous target and hindsight saved launches took 29.622 and 28.887 s elapsed through exit. The exploratory solve spent 1.159 s in observed graph construction and 15.596 s in cold discovery, versus 11.547 s of cold discovery on the earlier target. Salvage, signed repair and standard evidence also added work. The larger search time is part of this measured structural change and was charged.

Reopening every chosen slot spends **1.735 CPU s** at the measured dense short-aperture mean, and the policy spends 8.6 ms on the saved trace. Original full anchors, validation and all other ingress remain charged. The original native mask saving of 4.735 s falls to 2.992 s after this work. Adding the saved numerical solve gives **61.896 CPU s** estimated acquisition-plus-solve versus **58.508 s** full mixed, an increase of **3.388 s**. This model leaves out time waiting on original I/Q, startup and figure publication. The actual saved process clock above includes its figures and exit. This is one exploratory dense recording, with no additional physical or simulated publication, raw receiver call, uniform solve or displaced-region replay. [Aperture clocks and source proof](measurements/dense-full-short-raw.json.gz)

The one-fit protocol and runner were frozen at `ca9cb25f9`. Six owned and adjacent tests passed. The candidate ran against the authenticated tmpfs inventory and read-denying waveform hooks from the previous owner-recovery worker. It used the shared Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread. Invoke `causal_mask_dense_trial.py run FRESH_TMPFS_DIR` and then `causal_mask_dense_trial.py score FRESH_TMPFS_DIR SCORE.json`. The receipt expands to SHA-256 `d121d41433609e13bb4c1a482406b2ea57f0ead08fb9af712e78b5b1ede60dc1`. [Runner and score](causal_mask_dense_trial.py) · [Exact purchase and restoration tests](../../../tests/pipeline_eval/test_causal_mask_dense_trial.py)
