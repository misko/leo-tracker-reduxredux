# Explicit transition from constrained discovery to fitted calibration

Iteration 148's zero-c discovery states carry saved convergence flags, but all
three failed the downstream calibration gate. Source inspection suggests an
unsupported transition from a constrained optimum to a free-c stationarity check.
Independent qualification of the original zero-c states has not yet been measured.
This successor preserves the failed experiment and the original regions, scores,
and states. Preparation includes no recording-model calls.

Both fresh branches follow the same rule:

1. Recompute the original coarse objective and independently check feasibility
   and stationarity under both the discovery arm and the fitted-c arm, holding
   position fixed. Record both checks regardless of the saved convergence flag.
2. Reject an unqualified discovery state. If only the free-c check fails, call
   iteration 102's existing qualifier once, allowing at most two rounds and 100
   objective evaluations.
3. Independently qualify the promoted fitted-c state, then run the unchanged
   iteration 103 calibration and iteration 105 regional recovery/B7 stages.

The transition changes neither the candidate position nor the slope bounds,
retained-region ordering, or qualification threshold. The original discovery
payload and its hash remain unchanged. The replacement recovery port clones the
function environment without mutating the loaded production modules.

The native control follows the same rule and is expected to need no repair;
unexpected repair is still recorded. Both branches retain the existing 25 km
local radius, at most six 500-second slices, exclusive stage claims, and no
silent retries. They use fresh output paths. Reference-based evaluation is
allowed only after both branches terminate. Full-state native control parity is
checked against the historical result.

The frozen protocol inherits and verifies iteration 148's source/input bindings
and adds this successor's source closure. Calibration receipts preserve the
original fit, both stationarity checks, repair cost, promoted state, and expected
downstream assertion/value failures. Errors during the diagnostic itself remain
explicit stage failures rather than admitted fits.

The coarse Hard60 vector contains static c only. RF-time coefficients are
introduced downstream; the unchanged B7 zero-c final arm also locks both RF-time
terms. Observations, satellite support, other priors, and search budgets remain
matched between final c arms within each discovery branch.

Diagnostic overhead is two objective evaluations at the original state and one
at a successfully promoted state. This excludes the original objective
verification, the downstream postfit check, up to 100 repair evaluations, and
unchanged calibration/fitting work; it is not a three-evaluation stage budget.

This is one previously consumed DS18 scan. It cannot establish general accuracy
or justify deployment alone. No new cohort or reserve outcomes are opened.
