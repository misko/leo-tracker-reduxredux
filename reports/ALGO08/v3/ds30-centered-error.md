# DS30 position-error spread after removing each build’s mean

On the 13 shared scored captures among the first 16 verified DS30 pairs, the candidate’s centered horizontal RMS was **1.622 km versus 0.886 km** at fixed `c = 0`, and **1.517 km versus 0.812 km** at fitted `c`. The candidate’s mean offset magnitude was smaller in both arms. A common displacement leaves centered spread invariant, so removing each build’s own best constant offset leaves substantial excess error on this cohort. [Frozen scope and methods](ds30-centered-error-protocol.md)

| Calibration and build | Shared scored captures | Radial RMS (km) | Mean offset magnitude (km) | Centered RMS (km) | Radial MSE (km²) | Squared mean offset (km²) | Centered MSE (km²) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed zero, installed ALGO08v3 | 13 | 0.933 | 0.292 | 0.886 | 0.871153 | 0.085502 | 0.785651 |
| Fixed zero, candidate | 13 | 1.638 | 0.228 | 1.622 | 2.682317 | 0.051790 | 2.630526 |
| Fitted, installed ALGO08v3 | 13 | 0.851 | 0.255 | 0.812 | 0.725006 | 0.065238 | 0.659768 |
| Fitted, candidate | 13 | 1.533 | 0.224 | 1.517 | 2.351452 | 0.050126 | 2.301326 |

At fixed zero, the candidate adds **1.811164 km²** of radial MSE. The centered term rises by **1.844876 km²**, while the squared mean term falls by **0.033712 km²**. For fitted `c`, **1.626446 km²** of radial excess comprises **1.641558 km²** more centered spread and **0.015112 km²** less squared mean offset. Centered RMS rises by **0.736 km** and **0.705 km** respectively, even when each build is granted its own in-sample mean.

Installed ALGO08v3 produced 13 scored fixes out of 16 assignments, with two withholds and one signed solver failure. The candidate produced 14 scored fixes and two withholds. The shared denominator of 13 is identical for both calibration arms and excludes the two shared withholds and the candidate-only fix on DS30-0397. Those three captures remain in the assignment and fix counts. The verified original DS30-0452 relocation contributes to the common denominator.

Each signed local east/north offset uses its own enrolled operator reference and the radial distance from the standard scoring sphere. Offset lengths matched the standard errors to within **8.89×10⁻¹⁶ km**. The finite-sample identity `mean squared distance = squared mean offset + mean squared centered spread` and the equivalent sum of pairwise squared distances divided by `n²` both held within **4.45×10⁻¹⁶ km²**. Centered spread uses denominator 13. No estimate, reference or mean-vector coordinates enter this report or its receipt. The calculation describes the chosen recordings at one Gauss site without assumptions about independence, cause or transfer to other sites. No scientific output was adjusted. [Pure projection and decomposition](ds30_position_moments.py) · [Exact receipt](measurements/ds30-centered-error.json.gz)

DS30-0105, DS30-0244 and DS30-0183 were reserved before endpoints were opened and lack verified pairs in the enrollment snapshot. No prospective aggregate is reported. The initial protocol was committed at `936a89087` and verified analysis source at `3234d2331`. Rerun `python -m reports.ALGO08.v3.ds30_centered_error --snapshot SNAPSHOT` with the frozen combined-export and seal files and read-only access to the original pair receipts. The uncompressed result SHA-256 is `71ea4041f90fba34af3745582c6d217c5ae3fa1a1cbdfe545ca97cbcdade1e09`. Twenty-six focused and adjacent report tests passed. [Read-only analyzer](ds30_centered_error.py)
