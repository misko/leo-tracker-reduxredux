# Complete C019 coverage comparison at 60 seconds

The matched four-start diagnostic established strict convergence at 60 seconds for all four tested initial states, versus none at 20 seconds. It did not establish good localization or cover the full prespecified search inventory. This continuation completes that original inventory with the same 60-second allowance.

The full comparison contains 44 unique calls: original native and native common-clock models, each with six original endpoint starts and all sixteen original coarse-grid starts. Every call uses its previously qualified initializer, the fixed 67-satellite bank, fitted c, original priors, 600 iterations, and strict KKT threshold 0.001. Original endpoints retain their 25 km disks; coarse starts retain 100√2 km disks and the original 250 km global prior. No starts are selected using reference distances.

Four exact 60-second calls from `ds22-c019-coverage-budget-v1` are inherited with their seeds, options, raw fits, audits and timing records checked. Only the other forty calls are attempted in this namespace. No 60-second endpoint is repeated. Original 20-second failures remain immutable, and they are not initialization sources.

Each new unit contains one bounded fit: 180 second internal orchestration limit, TERM at 195 seconds and KILL at 200 seconds. Six single-thread workers execute the finite forty-call queue. Preparation and final authority checks are separate from the 60-second scientific fit limit. Every returned fit retains CPU and wall durations; throughput and availability can depend on host load even when CPU/wall ratios are close to one.

The global seal requires all forty new receipts plus the four inherited outcomes, rejects duplicate or unexpected unit inventories, and independently recomputes the training-score selectors. Each model has an original-six selector and an all-twenty-two selector. No cross-model objective ordering is used. The evaluator requires the full seal before reading the configured reference. DS22 reference coordinates remain unconfirmed, so any reported distance is not verified accuracy.

Driver source `d58ba1078` passed four component tests and Ruff. Evaluator source `61b669bb2` passed its pre-seal reference guard test and Ruff. Scientific output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-full60-v1`. This pilot does not change the completed DS21 cohort histogram or establish the cohort-wide accuracy target.
