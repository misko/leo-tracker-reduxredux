# Compact physical receiver clock

The compact oscillator uses 12 radio coordinates against the full smooth clock's 30. It retained the same total number of published fixes on 135 recordings and rejected all nine wrong offers. It raised median geographic error by 141 m and 200 m among each method's published fixes. On the 118 recordings published by both methods, the median paired increase was 24 m and 30 m. Backend wall time fell by 88 ms at the median, and whole-worker wall time was similar across the separately timed replays.

## Physical model and measurement

Each receiver has one fractional-frequency curve, continuous and linear between five fixed knots at 0, 75, 150, 225 and 300 s. The mid-capture frequency is anchored to zero, leaving four oscillator coordinates per receiver. Four static mixer offsets preserve the existing low/high group and alias convention. The oscillator scales by RF divided by 11.5 GHz. The same optional static RF-linear coefficient remains available in the fitted arm.

The first oscillator degree of freedom is the secant rate with a 10 Hz/s Gaussian standard deviation taken from the pinned v5 shared receiver prior. The other three degrees of freedom parameterize second differences. For integrated white acceleration, a second difference is a triangular integral. Neighboring triangles share one quarter of the normalized covariance. The 518.414 Hz second-difference standard deviation matches the mean knot-difference variance of the pinned 200 Hz smooth clock prior. These quantities were locked from the physical source before geographic scoring. The oscillator describes RF frequency on the original sample clock.

All 144 attempts consumed complete authenticated native GLRT packets. The compact and full smooth worker reproduced the same peak counts, Graph digests, training and final assignment, aliases, and robust weights. The unchanged shortlist and three exact orbit/location relinearizations determine the position. The held predictor freezes the state estimated from training blocks and scores the original held tracks. This is a within-capture holdout with training blocks on both sides of held blocks. The final geographic fit uses the complete retained assignment. Publication gates, including the existing training-anchor and geometry comparisons, remain identical.

## Geographic comparison

Each cell lists the zero and fitted calibration arms. Error medians and p90 values use published coordinates. The within-1 km count uses all 135 scheduled true offers.

| Receiver | Published | Median error (km) | P90 error (km) | Within 1 km |
| --- | ---: | ---: | ---: | ---: |
| Compact clock | 119 / 119 | 1.671 / 1.484 | 3.433 / 3.692 | 34 / 37 |
| Full smooth clock | 119 / 119 | 1.530 / 1.284 | 3.461 / 3.629 | 35 / 41 |
| As-built native joint | 119 / 119 | 1.759 / 1.584 | 3.820 / 3.841 | 26 / 36 |
| Original no repair | 135 / 135 | 0.982 / 0.988 | 2.284 / 2.155 | 72 / 69 |
| Original selective gap | 135 / 135 | 0.980 / 0.953 | 2.284 / 2.155 | 73 / 70 |
| Original one omitted track | 135 / 135 | 0.980 / 0.988 | 2.284 / 2.174 | 73 / 70 |
| Original omitted tracks | 135 / 135 | 0.960 / 0.958 | 2.239 / 2.174 | 74 / 71 |

Two publication decisions diverged from the full smooth clock in both arms. The compact model withheld DS26-0168 at its geometry gate and published DS26-0209. Across the 118 shared fixes it improved 53 and 58 cases by more than 1 m. Errors increased by more than 100 m on 49 and 50 cases. The largest paired increases were 2.33 km in the zero arm and 2.16 km in the fitted arm. All three native methods withheld both arms on all nine omitted offers. The standard transfer chart labels their forced coordinates as diagnostic.

## RF and cost

The compact model raised the paired median fit RF RMS by 9.63 Hz and 9.28 Hz on the 135 true offers. The held RF RMS shifted by +0.47 Hz and +1.57 Hz, with 66 and 65 recordings improving. The published geographic tail and the geographic gap to original v5 remain material despite similar held RF errors.

Within the compact receiver, fitting c decreased fit RMS on 132 of 135 roofs, with a median change of −24.95 Hz. It changed held RMS by −11.35 Hz at the median. Among 119 published fixes it improved geographic error on 69 and worsened it on 50, with a median paired change of −40 m. The coefficient comparison uses the same retained observations, orbit assignments and fit budget in both arms.

All jobs completed in 224.0 s of supervisor wall time under the four-lane schedule and 512 MiB address-space cap. On the 135 true offers, median worker wall and CPU time were 6.101 s and 5.577 s for compact, compared with 6.031 s and 5.679 s for archived full smooth. Median backend wall time was 2.357 s and 2.445 s, respectively. A complete worker includes factor read, peak selection, Graph, catalogue propagation and the solver. Peak resident memory was similar, with medians of 140.7 and 140.5 MiB. These are separately timed replays on the pinned host lanes.

The report includes all completed and withheld rows, the original-control execution bindings and the byte-sealed standard [roof and transfer chart inputs](figures.json).
