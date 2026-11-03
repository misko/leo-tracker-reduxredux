# Causal single-scan cross-band drift geographic screen

Freeze the eight fixed-position correction arrays without recalibration.
Retain RX1-fixed, symmetric and RX0-fixed allocations. RX1-fixed is primary
because it alone passed the pre-geographic held gate; the others are sensitivity
controls, not alternatives to select using geographic error.

Keep original causal banks, masks, timestamps, Student-t4/100Hz likelihood,
candidate mixtures and search bounds (-12,12)km EN and (-5,5)seconds timing.
Four starts per scan/arm: original same-scan training endpoint plus EN/timing
(-2,0,0),(0,0,0),(2,0,0). Use the existing L-BFGS-B settings and endpoint
gradient/finite-difference/boundary qualification.96 starts, each capped90s,
at most three single-thread workers. No retries or substituted starts.

Seal all24 selected endpoints (highest qualified training score) and all
failures before computing any geographic errors. Missing qualified outputs
remain failures, not removed scans. No baseline fallback policy is introduced.
Report all allocations against the same original eight single-scan baselines.
Primary advancement requires8/8 qualified outputs, at least6/8 paired wins,
and at least10% lower median position error. Report mean, P90 and maximum too.
A pass would require remaining-scan confirmation; it is not final promotion.
No new IQ, RF collection, orbit replacement or cross-scan position pooling.
