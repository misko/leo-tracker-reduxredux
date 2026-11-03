# Fixed-partition coherent pilot: blocked S03

The following is one TRAIN-only blocked interpolation pilot, not an all-five or production result. The fitted-c broadening gate is **not passed**. No held measurement selected an endpoint, parameter, partition or hyperparameter.

Fitted-c held singleton NLL changes 23146.608 to 23227.178; lower is better. Only 2/7 blocks improve. The coherent fitted endpoint is nonstrict. These mixed/negative outcomes do not authorize an all-five expansion.

| Policy | c arm | Strict KKT | Calls | Held new singleton NLL | Original shared NLL | Original classifier held / 1909 | Requested held / 80 | New latent held / 1909 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| independent | fitted-c | 0.0002824155021080803 (True) | 353 | 23146.608 | 23075.341 | 806 | 73 | 809 |
| automatic | fitted-c | 0.0019562802402654125 (False) | 446 | 23227.178 | 23161.099 | 803 | 70 | 808 |
| independent | zero-c | 0.0010813106228265584 (False) | 482 | 24056.237 | 23965.107 | 670 | 53 | 673 |
| automatic | zero-c | 0.00046340436923658634 (True) | 440 | 23461.146 | 23387.953 | 812 | 47 | 814 |

Gate details: `{"fitted_c_delta_held_new_singleton_nll": 80.5699881942528, "improved_blocks": 2, "meaning": "Development expansion only; root review required; no production/identity claim", "passed": false, "requirements": {"aggregate_new_singleton_nll_improves": false, "both_strict": false, "original_classifier_full_held_non_decrease": false, "original_classifier_requested_held_non_decrease": false, "seven_blocks_and_at_least_four_improve": false}, "total_held_blocks": 7}`.

fitted-c, original_shared: 46 new, 49 lost, 757 retained. On the same retained intersection RMS changes 163.17703482670615 to 159.87318536954155 Hz. The overall associated RMS is 163.98421782907235 Hz; its selected population differs.

fitted-c, new_singleton: 45 new, 46 lost, 763 retained. On the same retained intersection RMS changes 164.4755455863287 to 162.2611777771873 Hz. The overall associated RMS is 165.9501545215261 Hz; its selected population differs.

zero-c, original_shared: 310 new, 168 lost, 502 retained. On the same retained intersection RMS changes 196.47791626667592 to 184.26732809705416 Hz. The overall associated RMS is 196.38106166407914 Hz; its selected population differs.

zero-c, new_singleton: 309 new, 168 lost, 505 retained. On the same retained intersection RMS changes 197.27753691892607 to 184.95332583555748 Hz. The overall associated RMS is 196.96697189273118 Hz; its selected population differs.


Requested held windows remain evaluation-only and are never linking labels:

| State | Window | Original classifier / N | New latent classifier / N |
|---|---|---:|---:|
| independent_fitted-c | DSX01-007 | 23/26 | 23/26 |
| independent_fitted-c | DSX01-008 | 25/28 | 25/28 |
| independent_fitted-c | DSX01-009 | 25/26 | 25/26 |
| automatic_fitted-c | DSX01-007 | 20/26 | 21/26 |
| automatic_fitted-c | DSX01-008 | 24/28 | 24/28 |
| automatic_fitted-c | DSX01-009 | 26/26 | 26/26 |
| independent_zero-c | DSX01-007 | 3/26 | 3/26 |
| independent_zero-c | DSX01-008 | 24/28 | 24/28 |
| independent_zero-c | DSX01-009 | 26/26 | 26/26 |
| automatic_zero-c | DSX01-007 | 9/26 | 10/26 |
| automatic_zero-c | DSX01-008 | 24/28 | 24/28 |
| automatic_zero-c | DSX01-009 | 14/26 | 15/26 |
The exact four endpoints and then all four metadata-only predictions were sealed before held CFO scoring. TRAIN has2073 rows; HELD has1909 and the boundary has6. Requested HELD has80 points. The other555 requested points from the other four sources are untested here. No missing or unassigned point leaves a denominator.

Both policies use the same complete original public TRAIN seed,45 original candidates, free receiver-band constants and unchanged physical/q/clock/timing priors. c0 changes and fixes only the RF coefficient, conditional on fitted-c upstream discovery. Each refit has1000 actual calls/120 active seconds; one independent endpoint audit is a separately counted call. The broad regional research domain is used; the original production25km local disk is not imposed. Nonstrict results remain present and never become accepted by a relaxed threshold.

Automatic TRAIN-only450Hz/45s/24point segmentation produces a response-selected partition. Its selection likelihood is omitted: this is a normalized fixed-partition working likelihood, not a Bayes factor or proof of common emitters. HELD rows use only the proper new singleton marginal, with no held grouping. The original shared normalized density/classifier is reported separately. These are model associations, not verified satellite identities. Reference location entered only the separate post-seal diagnostic, never grouping, fitting, endpoint selection or the predictive gate.

`QUALIFICATION.md` records930 zero-fit objective checks plus8 metadata predictors. `evaluation.json` retains both scores, all roles/windows, block deltas and the gate; the evaluation NPZs retain per-point classifications and singleton NLLs. Raw training coherent groups have no invented per-row NLL. Better training fit alone establishes no geographic improvement.

![Paired held predictive results](held_predictive_comparison.png)

The original cold TRAIN terminal's795/1909 held assignments is a descriptive anchor from a different kernel and less continuation, not this pilot's matched causal control. The matched comparison uses both policies with the same singleton density. The configured station reference is operator-supplied; survey uncertainty is unknown. Position is reported independently of the predictive gate.

| State | Configured distance km | Common timing s | Relative timing RMS s | Inside original25km disk | Broad research feasible/strict |
|---|---:|---:|---:|---|---|
| independent_fitted-c | 6.847125 | 0.073644 | 8.414112 | False | True/True |
| automatic_fitted-c | 7.766519 | 0.337057 | 8.112254 | False | True/False |
| independent_zero-c | 8.515805 | 0.416190 | 7.965286 | False | True/False |
| automatic_zero-c | 6.255307 | 0.401200 | 7.382135 | False | True/True |

![Post-seal position and complete parameter summaries](state_parameter_comparison.png)

Plot receiver labels use human RX1/RX2, explicitly corresponding to native model indices0/1. The stored complete-state arrays retain native indexing.

The prespecified automatic linking and coherent working likelihood did not improve the fitted-c held forecasts in this pilot. The c0 full-count gain also loses requested-window coverage and has a nonstrict independent control, so it does not reverse that conclusion. This rejects broadening this fixed pilot policy; it does not establish that all temporal association models fail. No extra fitting, endpoint repair, threshold change or alternative grouping was used after these outcomes.

The separately sealed [original cold comparison](../original_anchor/README.md) uses the same original shared classifier on all predictions:

| Outcome | Held /1909 | New/lost vs original | Retained-pair RMS original→new Hz | Requested /80 | Requested new/lost |
|---|---:|---:|---:|---:|---:|
| Original fitted-c cold endpoint | 795 | — | — | 66 | — |
| Independent, fitted c | 806 | 46/35 | 175.19→161.17 | 73 | 8/1 |
| Coherent, fitted c | 803 | 59/51 | 175.27→157.45 | 70 | 5/1 |
| Independent, conditional c0 | 670 | 146/271 | 180.95→195.19 | 53 | 6/19 |
| Coherent, conditional c0 | 812 | 231/214 | 177.92→194.83 | 47 | 5/24 |

These descriptive gains against the original do not establish a coherence effect: the new policies also free band constants, change the density and receive additional optimization in the broader research domain. They do not override the failed matched predictive gate. Original held windows007/008/009 contain20/20/26 assignments; independent fitted-c gives23/25/25, while coherence gives20/24/26. All denominators26/28/26 remain unchanged. This anchor used one disclosed original-density replay, zero new fits/orbit queries/reference reads, and preserves model-identity switches as diagnostics.
