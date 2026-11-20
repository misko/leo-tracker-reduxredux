# Shared receiver clock on fixed anchors

The physical clock improved in-sample RF fit on all 134 roof recordings with two final solutions. Geographic results on the same anchors were mixed. Across 98 recordings where both methods published, the median clock-minus-linear error was +20 m and +16 m in the zero and fitted calibration arms. The mean changes were −163 m and −134 m, with gains concentrated in cases such as DS26-0120 and DS26-0014. The clock published 100 of 135 roofs and the linear fit published 108.

## Evidence and fit boundary

Each worker read and authenticated a complete original native factor packet and rebuilt the streaming Graph. It ran the original anchor shortlist, nomination, leave-family-out forecast and validation once. Both final methods used the same accepted full tracks, fixed aliases, starting fit, robust weights and three exact geometry relinearizations. The treatment used the sealed 22-column oscillator from the prior shared-clock study in the actual nonlinear position fit, including its RF scaling and regularization. The geographic publication thresholds applied separately to each fitted state. All 144 same-worker linear results reproduced the independent linear archive's exact decisions and arm outputs, with the same peak counts and Graph.

The publication gate continues to use the original c=0 fixed-linear forecast fitted to other orbit families' prefixes. The clock-aware held diagnostic uses all pre-gate nominees with sufficient other-family and same-lane prefix support. It fits the two models on those other-family prefixes, holds the target's nominated orbit and prefix alias fixed, then estimates the target phase from its prefix. Its suffix only scores the forecast. This gives a paired conditional holdout of the target suffix, with other-family prefixes potentially spanning later times in the same capture. The held diagnostic uses the anchor's tile-center linearized range-rate model and is separate from the publication gate and final fit.

## Geographic comparison

Each paired entry lists c=0 and fitted c. Geographic medians use published fixes, while within-1 km counts retain all 135 scheduled offers.

| Method | Published | Median error (km) | P90 error (km) | Within 1 km |
| --- | ---: | ---: | ---: | ---: |
| Shared clock on fixed anchors | 100 / 100 | 1.614 / 1.389 | 3.602 / 3.315 | 20 / 29 |
| Anchored linear fit | 108 / 108 | 1.800 / 1.579 | 3.815 / 3.676 | 20 / 28 |
| Original no repair | 135 / 135 | 0.982 / 0.988 | 2.284 / 2.155 | 72 / 69 |
| Original selective gap | 135 / 135 | 0.980 / 0.953 | 2.284 / 2.155 | 73 / 70 |
| Original one omitted track | 135 / 135 | 0.980 / 0.988 | 2.284 / 2.174 | 73 / 70 |
| Original omitted tracks | 135 / 135 | 0.960 / 0.958 | 2.239 / 2.174 | 74 / 71 |

Of the 98 common fixes, the clock improved 47 and 49 by more than 1 m, with 44 in each arm worsening by more than 100 m. The 12 changed publication decisions account for two gains and ten losses. All ten losses were at the unchanged geometry gate with the same anchors. Both methods withheld all nine wrong offers. The transfer chart labels any forced coordinate as a diagnostic.

The six prospectively designated roofs were DS26-0303, DS26-0219, DS26-0152, DS26-0050, DS26-0004 and DS26-0030. The four fixes returned by both methods improved by a paired median of 212 m and 500 m. The clock withheld DS26-0050 at the geometry gate and both methods withheld DS26-0030. The original v5 controls published all six with median error 0.676 and 0.713 km. This subset was reserved by opaque ID before any clock scores and excludes prior anchor confirmation cohorts.

## RF and cost

The clock lowered final fit RF RMS by median paired differences of 18.16 and 18.50 Hz. The separate prefix-only held diagnostic worsened by 27.68 and 25.78 Hz at the median across 135 roofs, and improved on 47 and 51 sites. The six reserved recordings showed paired held improvements of 13.73 and 16.30 Hz at the median. On the nine wrong offers, fitted RF improved in every case and held RF improved in one case per arm.

Within the clock fit, fitted c decreased final RF RMS on 129 of 134 roofs, with a median reduction of 23.42 Hz. The held diagnostic fell on 85 of 135 with a median paired reduction of 4.34 Hz. Geographic error improved on 52 of 100 published fixes and worsened on 48, with a median reduction of 35 m. The original anchor validation remains matched across those two arms.

All 144 paired workers finished in 198.7 s using four pinned CPU lanes and the 512 MiB address-space cap. The median paired roof worker took 4.934 s and peaked at 140.6 MiB resident memory. Across 134 attempted roof fits, the clock and linear final-fit sections took 0.121 and 0.088 s at the median, with a median paired increase of 26 ms. Whole-worker timing covers the shared factor read, Graph, anchors, both final fits and the separate held diagnostic.

The immutable predictions and source plan support the standard [full roof, prospective and wrong-offer figures](figures.json).
