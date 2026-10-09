# Prepared bounded timing-score diagnostic

Not frozen or run. Queue remains110, then111, then115 under parent scheduling.
No new fit, search, RF collection, truth-guided seed or position evaluation.

`run.py` imports without reading recording inputs. Its six states are extracted
exactly from the failed DS17-033107 rescue: base, two common-timing probes and
three saved Newton dampings. The prefit uses the original selected bootstrap
satellites and ordinary Hard60Objective, without receiver correction:107's
`verify_coarse` constructs the same model with its default receiver baseline.
Receiver correction happens later and was never reached for this failed prefit.
The driver retains the model baseline term in captured predictions and decomposition.

Before execution, the parent must create a reviewed protocol binding the complete
107 source closure (including native predictor binary/C++/Python sources),107
protocol bytes, DS17-033 candidate receipt and current115 sources. The protocol
must carry the exact107 member binding and six-state vector/objective identities.
No exclusion of native modules or numerical source mismatches is permitted.
The current runner requires that protocol and checks every listed hash before
an exclusive attempt claim; a preexisting claim prevents silent retry.

One120-second soft deadline begins before reconstruction. It is checked between
calls, so a single call can overrun: actual elapsed time is reported, without a
hard-timeout claim. At most six full objectives and six fixed-mask likelihood
calls occur. A private function namespace captures the real predictor output
inside each full objective, avoiding extra orbit predictions or global production
monkeypatches. Saved objectives must match before their diagnostics are accepted.

The initial implementation exports masks/cell/winding changes, objective/prior/NLL
decomposition and top10 row score changes. It does not yet expose horizon margins
but does compare the saved two-probe prediction finite difference with analytic
timing derivatives, separately for stable mask/cell/branch components. Horizon
margins remain unavailable; do not claim the complete PLAN.md instrumentation.
Synthetic tests verify exact
production likelihood decomposition, saved-state identity and pre-call budget
guard. No recording objective has been evaluated during preparation.
