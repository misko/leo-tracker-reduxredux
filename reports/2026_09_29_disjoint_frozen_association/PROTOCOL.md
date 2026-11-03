# Earlier-window donor association transfer

Freeze all nine ordered pairs: early→middle, early→late and middle→late within DS7, DS8 and DS9. Reuse the selected six-start contiguous N8 fits. Require disjoint scan identities and donor last start +300 s strictly before target first start. These are sparse windows of existing 24-scan pools, not newly reserved research-blind data.

At the donor's fixed location, initialize each target scan's timing from the maximum of its original 41-node training timing grid, then jointly refine only the target's eight timings with original L-BFGS-B tolerances. Require optimizer success, interior ±5 s timings, maximum gradient <=0.01 and finite-difference audit <=0.02. Target training observations may determine timing and soft probabilities; target held observations may not.

Freeze target candidate/background probabilities at that donor-location/target-timing endpoint. Optimize the previously tested tangent surrogate from two starts: the ordinary target fit and the fixed donor-location endpoint. Retain original geographic/timing bounds and qualification rules, recording all failures. Select by surrogate training score only.

Compare original-model training-conditioned held prediction and reference distance for three arms: ordinary target fit; direct donor location with target-fitted timings; and constrained refinement. Report all nine pairs and failure denominators. Donor position uses only earlier scans; target assignments are still learned from target training, so this is not independent satellite identification. Reused target windows make pairs dependent.

No tuning after outcomes, no new RF, no production changes. Per-dataset process cap 300 s, BLAS1. This is a diagnostic transfer test, not calibrated absolute accuracy.
