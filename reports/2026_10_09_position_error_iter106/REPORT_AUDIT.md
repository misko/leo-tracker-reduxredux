# Independent terminal result audit

Post-fit evaluation authorized after all148 members became terminal. No fitting,
optimization, alternate seed or reference-guided operational selection performed.
All2300 frozen numerical/input hashes match;148/148 receipts are complete,
592/592 raw fits independently qualify and no operational fallback is used.
Independently recomputed pooled mean/median/p95/worst from all paired evaluation
rows agree with summary.json to1e-12. Dataset membership remains63/51/34.

| Arm / metric |125Hz control |100Hz candidate |
|---|---:|---:|
| Fitted-c mean km |1.317354 |1.290684 |
| Fitted-c median km |0.863677 |0.804999 |
| Fitted-c p95 km |2.269173 |2.098582 |
| Fitted-c worst km |53.400741 |54.835462 |
| Zero-c mean km |1.679102 |1.665395 |
| Zero-c median km |1.115160 |1.106889 |
| Zero-c p95 km |3.177642 |3.046137 |
| Zero-c worst km |54.781204 |56.772570 |

Fitted-c mean improves about2.02%, below the predeclared5%; median improves about
6.79%. There are101 improved and47 regressed fitted-c rows. Zero-c mean improves
about0.82% and median about0.74%, both below5%;83 improve and65 regress.
Both arms add one >1km regression relative to the same archived endpoint, whereas
the matched125Hz controls add none. Thus the frozen regression-count gate fails
in both arms. Dataset-mean and relative-tail gates pass. **The globally narrower
width fails the predeclared decision criteria; retain125Hz.** The stricter
candidate/control zero-new-regressions sensitivity also fails, but is not used
as a substitute criterion.

The fitted125Hz control reproduces archive position metrics to numerical precision.
Zero-c shared fitted-derived starts produce a0.012631km mean increase versus its
archived own-arm endpoint; this is a separate refit/start effect, not a width effect.

## Worst paired regression and mechanism limits

Both arms' worst regression is **DS18-022**, `scan-fw-f1a32cacd910c005`, a previously
consumed DS18 member. Fitted-c grows53.400741→54.835462km (+1.434721); zero-c
grows54.781204→56.772570km (+1.991366) versus matched125 control.
The second largest fitted regression is DS18-031 (+0.384907km); second largest
zero-c is DS17-023 (+0.969302km). No reserve recording was newly opened.

DS18-022 has the same frozen bank, regional origin, observations, fitted-derived
physical/clock starts and fit budgets in both widths. This experiment does not
retry regional search, so narrowing cannot establish recovery of a previously
discarded correct region. All four fits satisfy unchanged independent KKT; the
tail regression is not a timeout or unqualified-final fallback.

| DS18-022 diagnostic | Fitted125 | Fitted100 | Zero125 | Zero100 |
|---|---:|---:|---:|---:|
| Posterior RMS Hz |108.565 |92.532 |110.395 |92.451 |
| Effective signal windows |452.202 |445.052 |450.271 |442.409 |
| Mean clutter probability |0.803305 |0.806415 |0.804145 |0.807564 |
| Timing penalty |8.130 |8.039 |8.058 |7.841 |
| Nuisance penalty |22.858 |33.791 |22.451 |31.949 |
| Clock/coefficient norm |743.888 |847.344 |613.710 |839.490 |

Narrowing reduces fitted conditional frequency RMS, increases nuisance use and
slightly reduces signal support while position worsens. Maximum-assignment labels
change on only0.522%/0.565% of rows fitted/zero-c. These observations support a
description of changed likelihood/regularization balance within the same bad
regional solution. They do not identify a hardware bias, prove independent noise
calibration or establish which particular nuisance coefficient causes the error.
Raw objective values across widths are normalized under different models and
must not choose an operational winner, even when the smaller-width score is lower.

## Reporting provenance limitation

The first report invocation failed on five completion documents absent as direct
106 source keys. The corrected reporting-only reader verifies their transitive
frozen51-result file hashes and canonical baseline document identities. This is
not a waived source check, altered numerical result or missing input. Preserve
the failed-report receipt and disclose the metadata-only provenance fix. Frozen
numerical sources, attempts and decision criteria remain unchanged.
