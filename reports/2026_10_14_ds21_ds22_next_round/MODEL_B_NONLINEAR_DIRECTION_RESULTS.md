# Model B: fixed displacements in the full nonlinear objective

The two worst original-version B cases now have full-objective checks of their
saved weakest joint timing/calibration directions. This is a diagnostic, not a
new fit or an accuracy improvement. Both original selected positions remain
unchanged. Every check uses fitted c, original observations, bank, priors,
randomized training partition, and original proposal-centered 25 km domains.

The prescribed steps were ±1 m, ±10 m, ±100 m and ±1 km. The direction was fixed
from the sealed observed-mixture tangent result before evaluation. No direction,
step, observation or candidate was selected from reference position. Every
point satisfied the original physical and nuisance bounds. No reference or
held observations were loaded, and there were no optimizer calls.

| Case / view | Saved tangent curvature | Full gradient curvature at ±1 m | Full objective increase at −1 km / +1 km |
|---|---:|---:|---:|
| 039 CH1–8 | 13.6114 | 13.4966 | 7.7478 / 4.6114 |
| 039 CH1–4 | 3.4602 | 3.4701 | 1.5880 / 1.6517 |
| 039 CH5–8 | 0.6611 | 0.6427 | 1.0357 / 0.6608 |
| 023 CH1–8 | 7.4329 | 7.3217 | 3.6800 / 3.8045 |
| 023 CH1–4 | 5.7997 | 5.8045 | 2.9519 / 2.6796 |
| 023 CH5–8 | 2.4086 | 2.4479 | 1.6726 / 1.1357 |

Curvatures are in objective/km². The full gradient curvature is the central
difference of directional gradients; it includes actual orbit interpolation,
mixture and calibration evaluation. The tangent omits nonlinear orbit terms.
Near the original solutions they agree closely on the checked directions.
At one kilometre, nonlinear changes matter more: 039/high's full gradient
curvature is 2.4053 versus the saved local 0.6611. The direction is not reprofiled
at displaced points, so these are fixed-path costs, not optimized profile costs.

No checked displacement is downhill. This does not prove global optimality,
correct satellite identity, a physically correct timing model, or accurate
geography. It supports the preceding local confounding analysis and weakens a
simple derivative-error explanation on these specific directions. A different
geographic mode or systematic model error remains possible. Tightening a timing
prior solely from reference error is not justified by this result.

The runs completed in 19.552 s (039) and 15.821 s (023), including training
preparation. Each used 27 objective/gradient calls: one baseline plus eight
displacements for each of three views. Both had 180 s internal and 195/200 s
external TERM/KILL limits. Frozen source/input and original diagnostic seals
were verified before preparation and after evaluation. Local receipts are in
`local/model-b-displacement-039` and `local/model-b-displacement-023`, with
source snapshots and fixed pre-preparation protocols in each namespace.

The isolated component and adapter have ten passing tests, covering quadratic
closure, nonlinear remainder, infeasible-point refusal, actual B parameter
layout and original constraints. One formatting-only long-line lint finding
remains in the now-frozen component; no numerical source was changed after
either run. The implementation is research commit `16a74c58d`.
