# Native satellite-propensity likelihood port

The B conditional-development comparison motivates testing whether C's uniform satellite prior is also too restrictive. This implementation is only a pure native singleton likelihood port. It has no fitter integration or localization result, and does not change the active C satellite-offset experiment.

For each fixed detector branch, retain its normalized waveform-evidence weight, native receive time, visibility and original wrapped Gaussian. Let `p_s = softmax(logits)_s`, and retain the original fixed clutter mass `p0`. The raw native density is the original clutter density plus `(1-p0)` times the satellite/branch weighted signal densities. Its integrated mass is

`M_n = p0 + (1-p0) sum_s p_s sum_b waveform_weight_nb * visible_nsb`.

The explicit conditional alternative divides the raw density by `M_n`. Its NLL is therefore `raw_NLL + sum(log M_n)`. Zero logits reproduce the original uniform native likelihood in **raw** mode; normalized mode differs by this reported support correction and must not be called exact original-model nesting. Softmax satellite weights are not B's logistic probabilities constrained to sum to 1.6. This ports the modeling idea, not B's parameterization.

Analytic gradients include the visibility-normalizer derivative with respect to satellite logits. Prediction derivatives condition on the supplied visibility pattern; no differentiability across a visibility discontinuity is claimed. A common shift of all logits changes nothing, so any future fitting adapter needs an identifiable contrast basis. Temporal families are rejected; this port is for independent singleton windows only.

Nine component tests passed, covering original raw likelihood/posterior/prediction-gradient closure, nonzero logit and all native-prediction finite differences, logit-shift invariance, missing branches, no visible signal, temporal-family rejection, and numerical integration to unit density with full/partial/no satellite support and two unequal-weight native branches. Ruff passed. Source commit: `9cebf6a1e`.

The density conditions on the existing branch evidence and does not model how a detector selected peaks. There is no new accuracy claim, truth-derived weighting, fit, candidate change or held-data access. Actual-data qualification is being prepared on the two worst available original DS22 C cases, 019 and 075, before considering any model integration.
