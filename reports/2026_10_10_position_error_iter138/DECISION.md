# Consistent residual structure warrants a mean-bias diagnostic

All twelve consumed development members completed with both saved endpoints
reproducing their archived objectives within the frozen tolerance. All 35,206
observations had usable public acquisition metadata. Pairing retained 17,083
disjoint pairs and left 1,040 observations unpaired because no close neighbour
was eligible. No observations were replaced, and no new fits were performed.

The mean conditional score was 0.071549 for fitted-c and 0.364456 for c=0.
Every recording had a positive score in both arms. Of 96 predetermined
RX/channel/RF/edge groups, 93 had positive fitted-c sums and all 96 had positive
c=0 sums. Both alternating blocks were positive in 89/96 fitted-c groups and
94/96 c=0 groups; the remaining groups had opposite block signs.

This is evidence of recurring conditional residual structure under the existing
model. It is not a measured correlation coefficient, a calibrated significance
test, or evidence that a covariance model improves localization. The stronger
c=0 scores are consistent with a mean-model contribution, but do not identify
its physical cause. All nuisance parameters were fitted on the same recordings.

The next research step is the separately specified residual-mean versus product
decomposition in NEXT_DECISION.md. It should retain soft satellite weights and
the same acquisition pairs, and distinguish within-block centering from
cross-block mean predictions. No rho or per-scan physical model is selected.
The full-cohort phase reconstruction work continues independently.

The audit cost 209.264467 seconds of summed member runtime. The original failed
iteration 136 cost remains preserved separately; combined cost was 209.278822
seconds. Three subprocess namespace tests and two reporting tests passed in
parent review. Reporting verified the frozen source/input bindings, and the
archive retained all 24 raw result/claim receipts with readback hash verification.
The plot was visually inspected.

Production is unchanged. No position accuracy was evaluated in this audit;
the latest full 193-member fitted-c mean remains 1.254810 km, above the 0.4 km
goal. The pilot is consumed development data, not independent validation.
