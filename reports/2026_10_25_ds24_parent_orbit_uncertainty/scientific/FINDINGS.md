# Retained active-parent physical uncertainty: RF findings

Adding the missing physical prior materially changes the fast-scan RF problem,
but produces **zero qualified research candidates in four exposed cases**.
All 16 position fits completed, all final phase/Gamma checks passed, and every
unchanged cold baseline passed its paired RF gates. Every retained-uncertainty
candidate failed the conservative curved residual gates in both c arms. The
predeclared research policy therefore returns the exact original reference on
all four cases. The operational reference was frozen to that baseline
throughout. No geographic truth or position error was used in these findings.

The control adds one shared original three-mode Gaussian physical prior for
each active curved/predictive family lacking modes: 10, 6, 8, 9 families in
DS24-0010–0013, respectively. All old coordinates, phase priors, native
likelihood IDs, candidates, aliases, powers, noise and predictive-only roles
remain unchanged. New mode means are nuisance posterior diagnostics, not
qualified orbit corrections. The full marginalized likelihood retains them;
the conservative gate/extension view omits their means and retains the
original support set and thresholds. Literal expanded-support/full-mean gates
are separately saved and also reject all four pairs. Their legacy postfit
extension is explicitly unavailable because its contiguous-mode indexing does
not apply to this appended layout. This is a control of the existing
all-candidate uncertainty mechanism in the current pipeline, not a new general
orbit-error model or an identity test.

All eight fixed-state contexts passed zero-extra-variance replay, original
column/ledger preservation, predictive-value redaction, repeated
calculate→gate→extension→calculate invariance, actual-gradient step convergence,
mean-Jacobian convergence and dense shared-kernel checks. Primary information
holds the OLD Jacobian, weights/Gamma, mean and prior precision fixed and adds
only B B'. Information loss is positive semidefinite as required. The independent
fixed-state audit reproduced it to 3.97e−15 relative and the normalized dense
Gaussian density to 8.33e−9. This local Gaussian information is conditional and
does not supply calibrated uncertainty or the nonlinear objective Hessian.

| Scan | RF movement proxy, c0 / fitted (m) | Old-weak variance increase, c0 / fitted | Actual raw candidate shift from matched cold, c0 / fitted (m) |
|---|---:|---:|---:|
|0010|130.46 /140.34|19.88% /19.93%|178.58 /188.82|
|0011|19.02 /10.36|1.52% /1.66%|21.58 /11.15|
|0012|41.24 /24.18|24.99% /24.98%|54.42 /29.89|
|0013|83.30 /79.60|3.94% /3.99%|95.04 /90.66|

The proxy is −0.5 I_old^-1 Δg, where Δg is the change in actual −2ELBO
gradient. It allocates work and is not a predicted geographic error. The
predeclared both-arm 50 m OR both-arm 5% variance triage passed on 0010, 0012 and
0013; root then authorized all four matched cases. No cases or criteria were
chosen after geographic evaluation.

Full-likelihood conditional RMS improves slightly on every raw candidate arm.
After omitting the newly inferred physical means, conservative residual RMS
increases instead. The optimized total score worsens on 0010, 0011 and 0012 and
improves on 0013. Score and frequency residuals therefore give distinct results;
neither demonstrates geographic improvement.

| Scan | Optimized candidate minus cold-baseline −2ELBO, c0 / fitted | Conservative failed curved sources, c0 / fitted | Lost original accepted IDs, c0 / fitted |
|---|---:|---:|---:|
|0010|+2.949 /+3.047|4 /3|0 /0|
|0011|+0.657 /+0.758|1 /1|20 /20|
|0012|+1.832 /+1.399|1 /1|0 /0|
|0013|−3.584 /−1.745|2 /1|0 /0|

These rejections are present in the conservative view with the **original
support set**, so they are not newly activated owner vetoes. All 14 rejected
curved source-arm rows out of 538 fail conditional noise structure; all 200
explicit predictive source-arm rows pass. Examples include 0011 RX1/CH4/T003
with conditional mean z 9.19/8.23 and quadratic BIC gain 36.59/33.64; 0012
RX2/CH4/T003 with mean z 5.08/6.09; and 0013 RX1/CH3/T006 with conditional
RMS 498 Hz, mean z 8.40/8.29, slope z 3.16/3.17 and quadratic BIC gain
39.37/39.35. These are structured residuals, not a noiseless millihertz ACF
corner case. 0011 additionally loses 20
postfit-only IDs in each arm. Original curved/predictive likelihood membership
is exact everywhere. Accepted-union counts retain original likelihood IDs even
for failed raw endpoints, matching archived ledger semantics; separate raw
gate-accepted IDs prevent those counts from implying qualification.

Science used 12.42 s fixed-stage wall time and 49.46 s fit-stage wall time;
21.55+80.46 worker-seconds plus the owned numerical tests, about 102.02 s total
against the frozen 600 s cap. All cases remained below 120 s cumulative. No
runtime failures, retries, rescues, re-nominations, prior tuning or backfill
occurred. Independent [preflight](../audit/preflight.json),
[fixed-state audit](../audit/fixed_terminal.json) and
[terminal RF audit](../audit/terminal.json) passed. Any later geography is
reported separately.

The result establishes that omitted physical covariance affects this local RF
inference and that the declared conservative operational qualification does
not admit these four candidates. It does not establish that the prior is
physically calibrated, that the inherited associations are correct, that new
mode means are measured orbital corrections, or that a different gate should
be waived. The four cases were development examples before this study.

Artifacts: [protocol](protocol.json), [fixed outputs](fixed_summary.json),
[fit outputs](fits_summary.json), [full RF table](rf_report/RF_table.csv),
[fixed-state figure](rf_report/fixed_state.png),
[score and residual figure](rf_report/fit_RF_changes.png).
