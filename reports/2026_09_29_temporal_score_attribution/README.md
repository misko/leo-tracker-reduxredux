# Cross-time score disagreement is not a uniform geographic pull across receivers

Exact training-gradient attribution across 4,328 tracks in 72 scans finds
mixed receiver directions. After locally accounting for each scan's shared
timing offset, RX0 and RX1 window-level geographic gradients have negative
direction cosine in five of nine windows. The result does not support treating
the observed disagreement as one uniformly aligned geographic correction.
It does not identify a physical receiver, oscillator, orbit or association fault.

| Dataset / window | Tracks | Raw RX direction cosine | Timing-profiled RX cosine | RX0 / RX1 profiled gradient magnitude | Top ten tracks' share of gross gradient norm |
|---|---:|---:|---:|---:|---:|
| DS7 early | 486 | +0.753 | +0.983 | 181.15 / 42.51 | 13.0% |
| DS7 middle | 464 | −0.088 | −0.231 | 59.96 / 65.53 | 11.2% |
| DS7 late | 484 | −0.648 | −0.387 | 87.56 / 158.82 | 13.8% |
| DS8 early | 485 | +0.727 | −0.071 | 92.28 / 80.11 | 9.9% |
| DS8 middle | 464 | +0.638 | +0.551 | 41.04 / 42.12 | 14.5% |
| DS8 late | 485 | +0.931 | +0.898 | 69.92 / 100.34 | 14.3% |
| DS9 early | 491 | −0.836 | −0.573 | 23.69 / 39.53 | 13.3% |
| DS9 middle | 485 | +0.698 | +0.610 | 19.46 / 74.71 | 15.5% |
| DS9 late | 484 | +0.610 | −0.140 | 64.31 / 20.62 | 16.7% |

A cosine of +1 means aligned, zero means perpendicular, and −1 means opposite.
Gradient magnitudes are training log-score units per model kilometre, not
metres of error or calibrated confidence. Each window contains eight scans.
The nine windows share model construction and source fits and are not nine
independent experimental replications.

## Why both raw and profiled directions matter

The attribution is evaluated at each dataset's unchanged N24 source training
fit. Each track's original q020 training score is evaluated independently.
Let g be its east/north/time gradient and H the scan's observed negative
Hessian from the preceding audited diagnostic. Its profiled contribution is:

```
g_position − H_position,time / H_time,time × g_time.
```

Apply that same linear operator to every track within the scan. The resulting
track contributions sum exactly to the previously computed scan contribution.
This preserves the shared timing nuisance definition; independently fitting
one timing per track or receiver would answer a different question.

Profiling changes RX direction materially in some windows: DS8 early moves
from +0.727 raw to −0.071 profiled, and DS9 late from +0.610 to −0.140. Thus
receiver alignment depends partly on the treatment of shared timing. These
are local derivatives at a pooled fit, not receiver-only location estimates.
Even a common frequency-domain error can map through different geometric
sensitivities into different geographic gradients. The table cannot rule out
a common physical error or prove independent receiver defects.

## RF and track concentration

The [summary](summary.json) retains vectors and directional comparisons for
every exact stored RF center in every window. There are 8–16 such centers per
window, including small center-frequency offsets; these are metadata groups,
not asserted physical transmitter identities. Contributions include both
aligned and opposing directions within every window. Do not collapse them to
one dominant-frequency claim based on cosine alone, which lacks magnitude.

The ten largest track contribution norms account for only 9.9–16.7% of gross
norm in each window. This statistic uses sum of individual vector lengths,
not the norm of the cancelling vector sum. It does not show that removing ten
tracks has a small effect on location, nor identify those tracks as outliers.
No track, receiver or RF center is excluded or downweighted here.

## Verification and consequence

All 4,328 eligible source tracks are included: 1,434 DS7, 1,434 DS8 and 1,460
DS9. All 72 per-scan sums replay their stored training gradients exactly,
scores within 7.28e−12 and timing-profiled gradients within 7.11e−14. A synthetic
test verifies additivity of the profiling operator. Source hashes and Ruff
checks pass. All three workers exit zero in 14.4–15.3 seconds, under 120-second
caps. No target score or geographic reference enters the attribution.

This diagnosis narrows what the earlier selection result establishes. Balancing
aggregate scores compresses a pooled fit partly by preserving cancellations;
it does not demonstrate that the retained measurements share one physically
correct correction. A calibration proposal should predict signed residuals on
excluded receiver/time/RF groups before geographic fitting, with the original
shared timing convention controlled. Gradient agreement alone is insufficient.

No new location fit or accuracy improvement is claimed. See [protocol](PROTOCOL.md),
[study](study.py), raw per-dataset contributions and process receipts. No RF
collection, production edits or publication occurred. Artifacts are local.
Reproduce with `study.py prepare`, `study.py batch`, then `summarize.py` under
a NumPy/SciPy interpreter in a fresh output context.
