# Staged full-FOV sweep through 90 degrees

The frozen extension completed in 132.05 seconds for the same five cells, twelve
TRAIN scans, and 774 tracks per cell. The table reports supported tracks and
occupied-second coverage for one receiver mapping; the exchanged mapping is
numerically identical because its axes are related by 180 degrees of yaw.

| cell | 10° | 20° | 25° | 30° | 40° | 50° | 60° | 70° | 80° | 90° |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cell 1 | 14 (.8%) | 100 (8.3%) | 207 (18.3%) | 302 (30.3%) | 476 (54.6%) | 592 (69.7%) | 663 (80.6%) | 684 (83.3%) | 698 (85.4%) | 709 (87.0%) |
| cell 2 | 17 (.9%) | 110 (9.2%) | 192 (17.2%) | 289 (28.2%) | 462 (50.6%) | 569 (64.5%) | 624 (71.6%) | 633 (72.5%) | 653 (75.9%) | 661 (76.9%) |
| cell 3 | 17 (1.0%) | 114 (9.7%) | 205 (19.5%) | 317 (33.5%) | 528 (62.2%) | 655 (81.7%) | 724 (91.5%) | 739 (93.3%) | 743 (93.8%) | 744 (94.0%) |
| cell 4 | 18 (1.1%) | 94 (7.4%) | 181 (15.5%) | 303 (31.1%) | 487 (54.1%) | 588 (68.2%) | 644 (76.5%) | 666 (79.5%) | 678 (80.8%) | 680 (81.1%) |
| cell 5 | 19 (1.1%) | 117 (9.9%) | 203 (19.5%) | 317 (33.4%) | 523 (61.5%) | 651 (82.2%) | 728 (92.7%) | 744 (94.6%) | 747 (95.0%) | 749 (95.3%) |

Across cells, supported coverage rises from .8%-1.1% at 10 degrees to
76.9%-95.3% at 90 degrees. At 90 degrees, supported track counts range from 661
to 749, all-track held capped loss from .172 to .473, and supported-only held RMS
from 296 to 499 Hz. The broader cone admits more of the ordinary Doppler
candidates; this does not by itself identify a location or calibrate antenna
gain.

The five cells are frozen labels from the earlier TRAIN search:

- cell 1: 37.695929, -122.655162; aliases `first_train/coarse50_rank1` and `second_train/coarse50_rank1`
- cell 2: 38.145258, -122.672795; alias `first_train/coarse50_rank2`
- cell 3: 37.902306, -122.396012; alias `first_train/final_selected`
- cell 4: 37.708537, -122.087151; alias `second_train/coarse50_rank2`
- cell 5: 37.801848, -122.410239; alias `second_train/final_selected`

After all inference and width results were frozen, comparison with the existing
reference coordinate (37.849033, -122.485654) gives distances 22.623, 36.795,
9.849, 38.349, and 8.450 km for cells 1-5. None is the reference coordinate;
cell 5 is nearest. This post-seal evaluation did not select a width, orientation,
assignment, or cell and is not a position-accuracy estimate for the method.

A separate parity receipt verifies all 30 prior 10/25/30 cell/mapping cases,
including orientations, losses, support, changed IDs, and every refit candidate
ID. Every selected assignment also retains its maximum training angle for direct
half-angle auditing. No truth entered fitting, and no VAL/TEST, new RF, QNAP
write, or deployment was used.
