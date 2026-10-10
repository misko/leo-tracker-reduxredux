# Full-cohort phase comparison draft

This draft is contingent on complete iteration 137 ordinary endpoint parity. It is not a frozen experiment, and authorizes no fits.

Retain all 193 development members and their exposure classifications: DS16 63, DS17 51, DS18 34, newer development 45. Existing reserve outcomes stay closed. The historical comparator is the latest selected iteration 107 candidate, preserving recovery and both independently reconstructed archive arms.

Apply the unchanged iteration 135 relative-phase conversion globally. Compare fresh timestamp control against phase using one common fitted-selected model per member: same observations, selected bank/order, receiver baseline, satellite centres, clock nodes, nuisance priors, 0.5 Hz/s satellite slope precision, and receiver constraints. All four fits use copies of the fitted-selected vector/clock; zero-c locks static c and the two RF-time coefficients. No fitted-versus-zero-c or timestamp-versus-phase winner is selected by reference error or per-scan score.

Each of four fits uses the existing 90-second, 600-iteration attempt and unchanged independent KKT qualification threshold 0.001. Iteration 135 explicitly checks maximum_iterations_per_fit=600; this is not an objective-evaluation cap. Preserve all raw failures and unqualified attempts; archived fallback is displayed separately from raw accuracy, without substituting it invisibly. Costs and terminal coverage remain explicit. Four attempts per member imply at most 772 planned fits, subject to successful physical input admission.

The existing iteration 135 comparator requires both archived endpoints to match one common model. The full-cohort successor must instead verify each archive on its own independently reconstructed model through iteration 137, and preserve archived zero-c as a historical comparator if model parameters differ. New four-fit controls share the fitted-selected model. Satellite ID agreement alone is insufficient to assume identical baselines, centres, or prior matrices.

Freeze numerical sources, clean inference identities and projection hashes, matched starts, budget, qualification, fallback, and all membership before execution. Report complete-cohort and per-dataset mean, median, p95, worst, paired regressions, convergence and fallback counts, plus frequency/prior/support changes separately. A better in-sample score cannot establish the correct physical timing convention. No deploy decision follows from the consumed pilot alone.
