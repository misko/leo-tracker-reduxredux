Native whole-path offset-prior variance diagnostic
=================================================

This predeclared sensitivity test changes only the marginalized whole-path
offset prior SD on newly recovered persistent5s native predictive paths:
300 Hz (existing), 600 Hz (diagnostic), and 3000 Hz (mean-uninformative extreme).
All graph-parent predictive entries retain 300 Hz. The shared curved-posterior
predictive covariance is retained through the original conditional_gaussian.
The original curved model/calibration normal equations, individual noise,
identities, aliases, observations, original residual gates, starting position
[0,0], zero starting phases and 5x48 Gauss-Newton budgets remain unchanged.
The new native observations still do not calibrate the receiver parameters.

No GPS appears in the fit script. report.py adds position error after inference.
No setting is selected or promoted from these results. Every saved endpoint at
300 Hz independently replays within 1e-5 objective error; every cold 300 Hz fit
exactly reproduces its saved ordinary endpoint objective.

DS23-0259 report-only position errors (c0 / fitted_c):

* 300 Hz: 3.562106 / 3.421311 km.
* 600 Hz: 2.878688 / 2.748375 km.
* 3000 Hz extreme: 2.056569 / 1.996406 km.

The common original-300-Hz full-mask objective worsens by 0.181167 / 0.186216
at 600 Hz and 0.965015 / 0.855784 at 3000 Hz. Curved RMS increases from
155.882 / 155.766 Hz to 156.250 / 156.143 Hz at 600 Hz and 156.747 / 156.583 Hz
at 3000 Hz. Thus lower reporting-only position error is not a better fit under
the original model. Scores under each prior's own normalization are included
for completeness but should not be directly interpreted as matched-model gains.

Controls show smaller position changes at 600 Hz: DS23-0041 -0.018010 /
+0.028621 km and DS23-0272 +0.020252 / +0.009708 km. At 3000 Hz, control changes
remain below 0.042 km. All 18 final fits pass existing gates, preserve every
accepted parent ID and retain the same accepted coverage within each recording:
678 (0259), 734 (0041), 1932 (0272). These observations support sensitivity to
native path means in 0259, not adoption of a new prior or calibration mechanism.

results.json contains all fit summaries, phase histories, entry-specific prior
vectors, gate/coverage results and common original-model scores. summary.json
and position_diagnostic.png are reporting-only derived artifacts. The original
fit source uses the frozen numerical helpers and a custom vector of path bias
SDs; it does not globally scale predictive noise.

Two owned tests pass in 1.65 seconds. They check default shared predictive
density/residual equality, only-new-entry prior changes, original endpoint
replay, cold300 reproduction, fixed five-round budgets and parent ID preservation.

Execution correction: an initial 18-fit run was repeated after discovering that
a reporting-only common-model score had reused a cached endpoint evaluation.
The final source rebuilds the model before scoring under 300 Hz. Consequently
36 tiny bounded fits were executed in total, exceeding the requested maximum
of 18; the saved final grid has 18 fits. Individual fits took about 1–2 seconds
and each retained a 180-second alarm. No further fits were run. No old artifacts,
production behavior, gate thresholds, or scientific fixtures were changed.

Use the parent solver0365/README.md environment, then execute run_bias.py,
report.py, and pytest test_bias.py. Do not use these diagnostic priors as a
production recommendation without independent review.
