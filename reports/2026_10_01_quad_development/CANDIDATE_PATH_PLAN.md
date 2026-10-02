# Radio-only candidate-path feasibility

Use only the 80 selected DS10 pair probe groups and their public margin-passing candidates. This is an outlier-selected feasibility study. Do not change frozen measurements or evaluate location. Keep one candidate per source group, chronological order, and exact candidate timestamps. No satellite prediction, orbital state, GPS, or fitted localization residual enters selection.

Resolve coarse aliases by choosing for each candidate the integer lift nearest the original exported radio track at that probe. Thus the search is conditional on the original coarse frequency band, not a fresh global trajectory reconstruction. Disclose this dependence. The RF normalization and scaled alias spacing come from the pinned public config.

For three consecutive candidates define dt1=t1−t0, dt2=t2−t1, r=dt2/dt1 and innovation e=y2−(1+r)y1+r*y0. Score e²/[sigma²(1+(1+r)²+r²)+(a*dt2*(dt1+dt2)/2)²], plus one candidate emission cost −0.1 log(margin/max margin in its group). Enforce adjacent slopes within ±15,000 Hz/s, matching the original broad trajectory bound. Exact second-order dynamic programming minimizes this heuristic score over the finite lattice. Overlapping innovations are correlated: this score is not a calibrated likelihood or posterior.

Freeze primary sigma=100 Hz, a=100 Hz/s². Controls: sigma=300 Hz with a unchanged; sigma=100 Hz,a=300 Hz/s²; margin-only selection. Constants are diagnostic assumptions, not tuned accuracy parameters. Report identity changes, path scores, quadratic detrended RMS and plots for both RX1 and RX0 control. Smoothness improvement alone cannot prove correct satellite identity. No automatic localization promotion follows, even if every path becomes smoother.

Tests must compare dynamic programming against exhaustive enumeration on a small candidate lattice and reject impossible slope support. Later development requires a frozen general policy, source-group exclusivity across simultaneous tracks, and metadata-selected block validation before singles/pairs/quads.
