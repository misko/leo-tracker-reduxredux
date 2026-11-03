# Frozen selection probabilities: calibration limitation

The previous predictive-transfer result is valid but does not establish
well-calibrated event probabilities. A descriptive audit now evaluates the
unchanged models on donor16's unused visits and the complete separate donor17.
It uses fixed probability bins of width0.1 and each observed receiver/RF group;
no model is refitted, threshold searched, or previous gate overwritten.

| Detector-score model | Donor16 held visits | Separate donor17 |
|---|---:|---:|
| Candidates | 5,984 | 11,912 |
| Predicted retention | 22.912% | 23.176% |
| Observed retention | 23.046% | 27.965% |
| Weighted absolute bin calibration discrepancy | 1.705 percentage points | 5.816 percentage points |
| Largest receiver/RF absolute rate discrepancy | 5.652 percentage points | 20.242 percentage points |
| Brier score | 0.165532 | 0.197468 |
| Receiver/RF baseline Brier score | 0.177002 | 0.203851 |

These rates use the frozen receiver/window weights, not unweighted raw counts.
The model improves Brier score as well as log score, yet has substantial absolute
probability discrepancies on the separate record. Aggregate rate agreement on
the within-record held panel does not establish cross-record calibration.
Visits and candidates are dependent; no confidence intervals or independent
sample-count interpretation are claimed. A coarse-bin calibration error can
favor a nearly constant baseline and must not substitute for proper-score
comparison.

Decision: preserve the successful predictive screen, but do not insert these
probabilities as physical missed-detection probabilities, inverse-probability
position weights, or hard receiver/sky exclusions. The labels still describe
track membership conditional on a margin-passing raw candidate. Unobserved
signals and catalogue-other/clutter events are not labeled by this experiment.
Further integration needs a model that handles recording/RF-dependent selection
and the distinction between candidate presence and satellite visibility, with
fresh validation for any changed specification. No DS11 position fit or accuracy
claim results from this audit.

Four component tests pass across the selection and audit code. New audit tests
cover endpoint/invalid probabilities and weighted group summaries preserving all
rows. Results and source bindings are in `calibration-audit.json`.
