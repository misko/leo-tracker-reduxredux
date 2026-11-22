# Causal Doppler revision directions at the public boundaries

One historical Doppler revision direction per satellite removed over 94% of the information distinguishing the two fixed faces at each site. The new score separated both noiseless faces in the south, with one failure after removing a satellite. In the north it selected B for both noiseless faces. The rule fails the prespecified advancement criterion. [Protocol](mirrored-revision-shape-protocol.md) · [Complete scores and omissions](measurements/mirrored-revision-shape-scores.json.gz)

The prior DSX01 prototype already tested a similar `old_new` covariance arm. It used the phase-aligned previous-minus-current state trajectory and projected its perturbation with a Student likelihood. The released ALGO08 position model uses three physical element modes. Here the fixed covariance column is the exact difference between the two causal retarded Doppler trajectories at the face midpoint, zero outside that NORAD’s rows. It preserves the direction discarded by whole-satellite weighting. The A/B means, track and phase nuisance terms, and every observation stay fixed. The coefficient prior retains unit variance on the unreweighted historical revision. [DSX01 prototype](../../../tools/prototype_dsx01_orbit_marginal.py) · [Released model](../../../src/leo/analysis/localization_v3/marginal.py) · [Whole-satellite weights](mirrored-orbit-weight.md)

| Site | Tracks / points / NORADs | Stereo RMS, Hz | Retained face information | Range after dropping one NORAD |
|---|---:|---:|---:|---:|
| North | 31 / 450 / 12 | 5.132 | 5.89% | 0.67% to 31.70% |
| South | 30 / 423 / 13 | 6.627 | 4.24% | 3.07% to 26.41% |

The information fraction compares the covariance-weighted squared A-to-B separation with its ordinary value after projecting out the same track offsets, receiver slopes and orbital phase tangents. The offsets absorb the fitted `c` column, giving the same comparison in both calibration gauges. The two saved simulations use distinct selected NORADs and share one later generator revision. The repeated A/B and omission scores reuse their respective single waveform. [Causal input lock](measurements/mirrored-revision-shape-lock.json.gz) · [Stereo scale receipt](measurements/mirrored-orbit-weights.json)

| Site and frequency source | Ordinary B − A loss, Hz² | Revision B − A loss, Hz² | Revision preference | Revision preference after dropping one NORAD |
|---|---:|---:|---|---|
| North, noiseless A | +8.17948 | −0.05547 | B | 1 A / 11 B |
| North, noiseless B | +6.94982 | −0.13415 | B | 0 A / 12 B |
| South, noiseless A | +4.51792 | +0.10479 | A | 13 A / 0 B |
| South, noiseless B | +1.51678 | −0.02220 | B | 1 A / 12 B |
| North, observed | +9.02638 | −0.03131 | B | 1 A / 11 B |
| South, observed | +2.02301 | +0.06839 | A | 12 A / 1 B |

Positive loss difference favors A. Both templates agreed on the alias lift at all 873 measured points. The public reference places each simulated receiver exactly at the midpoint of its two templates, so the observed preference is a conditional asymmetry at the boundary. In the ordinary score every observed omission preferred A at both sites. With revision directions the observed northern omission margins range from −0.09118 to +0.14638 Hz² and southern margins from −0.01483 to +0.22782 Hz². [Released reference coordinates](../regional-release/scoring-key.json) · [Per-orbit margins](measurements/mirrored-revision-shape-scores.json.gz)

Observed fitted frequency RMS for A/B fell from 8.802/9.301 to 5.153/5.144 Hz in the north and from 9.236/9.345 to 9.120/9.123 Hz in the south. Those residuals exclude the coefficient penalty, which remains in the face scores above. The experiment establishes that the historical directions account for frequency residuals while heavily attenuating the local face signal. It uses two previously examined synthetic geographies and yields no publish or withhold rule. [Full residuals and scores](measurements/mirrored-revision-shape-scores.json.gz)

The runner reuses the digest-pinned causal prediction, saved detections, tracking configuration and public archive. It verifies the historical revision magnitudes and the stereo scales against their earlier receipt. The input lock `7df0491d74802bb28504ca427b01a8c959ee305bcba411c1ce038fa16d90da7a` was sealed before a separate scoring process read the known later orbit. Both processes ran under the shared low-priority Gauss lock, and ten focused tests passed. [Runner](mirrored_revision_shape_trial.py) · [Component tests](../../../tests/pipeline_eval/test_mirrored_revision_shape_trial.py)
