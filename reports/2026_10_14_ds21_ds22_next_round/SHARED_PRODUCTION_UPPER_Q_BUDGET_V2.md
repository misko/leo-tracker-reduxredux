# Upper-edge production q budget: strictly accepted v2 result

The immutable upper-edge r1 canary had valid A/B sources but neither final shared-q fit passed strict convergence before its 15-second solver deadline. Replaying exactly those two complete zero-q source states under the versioned longer q-only budget yields **one strict accepted endpoint**, selected by its own training objective. This establishes a functional accepted inference result; no reference was read and no localization accuracy is claimed.

Runtime commit `f4d80d41e` changes the production identifier to `shared-scan-q-v2`. Only shared-q calls receive **60 seconds for the original solver / 65 seconds total / 4,999 optimizer objectives plus one reserved independent audit within 5,000 actual objectives**. Source fits retain their 15/20-second, 2,000-actual allowance. The whole production cap stays 1,200 seconds, with 130 seconds reserved for the two final shared calls. The objective, priors, source policy, own 25 km disks, 600 iterations and KKT threshold 0.001 are unchanged.

| Frozen source | r1 q J | r1 KKT | v2 q J | v2 KKT | v2 actual objectives | v2 seconds | Strict |
|---|---:|---:|---:|---:|---:|---:|---|
| A-5 | 58,897.714618 | 1,470.431006 | 58,377.966523 | 0.007933594 | 562 | 29.065 | No |
| B-all (original joint start 2) | 58,540.802301 | 2,306.385658 | 58,237.879820 | 0.000915812 | 531 | 28.698 | Yes |

The rejected A endpoint remains rejected. The accepted B endpoint wins training selection. Its NLL, complete state, independent audit and exact allocation are preserved in the original replay receipts; none of these scores is an accuracy metric.

The source-bound replay utility `215e43d6d` reconstructs original prepared observations, full causal TLE orbit bank, exact 65-satellite union, saved A-5 high shift and complete final state, and saved B-start-2 centered/raw correction transport. It checks the original input hash and every r1 stage hash/inventory before and after the run. It performs **zero discovery calls and zero A/B source fits**. It never starts from either failed r1 q endpoint.

Six qualification objectives compare both initial states with the immutable r1 mathematical source and independently replay the two failed r1 endpoints. The initial objective/physical-gradient/nuisance-gradient discrepancies are **exactly zero**. Initial J is 60,019.94107748462 for A-5, matching its saved r1 prescreen, and 60,001.12857157703 for B. Only after qualification are the two fresh q fits invoked. They consume **1,093 actual objectives**; with qualification, this replay consumes 1,099 objectives. Its whole runtime is 83.849 seconds within the 360/375/380-second envelope. It ran as `leo` through the immutable staged r2 Python wrapper with single-thread numerical libraries.

The replay's terminal and seal passed an independent metadata/hash/counter check. Twenty-four runtime component tests and two replay component tests passed; Ruff passed. Tests include exact numerical parity, source-budget preservation, q-only admission, solver-deadline return with independent audit reserve, complete saved-state reconstruction and added/changed parent-receipt rejection.

[Source-bound report JSON](shared_production_upper_q_budget_v2.json). Actual output: `/srv/bulk/leo/qualification/shared-position-20261016-r2/upper-q-replay`. The original unavailable r1 attempt remains untouched at the corresponding r1 `upper` path. Root owns the parallel lower-edge replay, fresh end-to-end r2 canary and production activation; this report does not assert those steps completed.
