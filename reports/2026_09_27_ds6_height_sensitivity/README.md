# DS6 fixed-height sensitivity

Positive trial heights do not improve horizontal error on any of the four
frozen development scans. No height correction or estimated antenna altitude
is adopted. These trials use WGS84 ellipsoidal heights; actual antenna height
and its datum remain unknown.

| Rate | 0 m error | 100 m error | 250 m error | 500 m error | 1000 m error | Training-selected height |
|---|---:|---:|---:|---:|---:|---:|
| 2.5 MS/s | 3.670 km | 3.816 km | 4.011 km | 4.328 km | 5.212 km | 1000 m |
| 5 MS/s | 8.482 km | 8.539 km | 8.616 km | 8.725 km | 8.863 km | 250 m |
| 7.5 MS/s | 0.505 km | 0.852 km | 1.381 km | 2.263 km | 5.258 km | 0 m |
| 10 MS/s | 4.950 km | 5.116 km | 5.370 km | 5.805 km | 6.678 km | 0 m |

The discrete training optima disagree, and three lie at grid endpoints. These
are sensitivity profiles rather than calibrated altitude estimates. Training
and held prediction improve at the selected positive heights for the 2.5 and
5 MS/s scans while geographic error worsens; this repeats the broader model
misspecification pattern. Zero altitude's better geographic scores do not
prove it is physically correct. Negative heights were not tested, and the
grid does not establish an error bound for arbitrary antenna altitude.

Each fixed height refits east, north and scan timing from three identical
starts, using corrected causal element sets, inherited candidate mixtures,
the same Student-t4 likelihood and training-profiled per-track offsets. The
random whole-visit masks remain fixed. Neither reference coordinate nor held
score selects fits. The separate summarizer reads reference coordinates only
after complete outputs and records source/result hashes.

All twenty selected winners converged within horizontal/timing bounds. Two
nonwinning starts reported abnormal line-search termination and are preserved.
Exact propagation checks are below 0.05 Hz. Tests verify WGS84 conversion,
zero-height model equivalence and held-data isolation, injected-height
selection at fixed horizontal position, and frozen full-profile provenance
and propagation. The conversion test initially supplied kilometres to an API
accepting metres; the test was corrected before data fitting, and its absolute
comparison tolerance tightened. The fitted geometry already used metres
correctly; no scientific fixture or result was changed to pass the test.

Independent-scan accepted performance remains 6/43 sub-kilometre, and the
corrected joint estimate remains 761.85 m. No production deployment or RF
collection occurred. A numerical offset-convergence audit is the next step
because the existing track-offset profiler always stops after 12 iterations,
without checking stationarity, and the prior covariance audit found three
locally step-sensitive scans.
