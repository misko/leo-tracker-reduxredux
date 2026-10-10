# Postseal `c` ablation: same-region B1 diagnostic

This is a source-only, predeclared analysis plan. It changes neither the frozen
iteration-164 numerical protocol nor deployed B7. Run it only after all 193
members and all 579 search/native/zero phase receipts pass the existing
postseal provenance gate. Reference coordinates and errors remain inaccessible
until that gate passes. Preserve every DS16/DS17/DS18/newer member, including
failed phases; do not re-run, replace, or exclude a member because of its error.
The separate `C_ABLATION_FREEZE.json` pins this plan, the extractor and its
tests, the postseal gate, and both frozen protocols before that analysis runs.

## What the existing run identifies

The two discovery queues use different `c` arms and can retain different
positions ([ports.py:8,23-31](ports.py); [search.py:93-129](../2026_10_09_position_error_iter129/search.py)).
Within **one** retained region, however, recovery associates satellites once,
builds one corrected `Hard60Objective`, and fits both `zero-c` and `fitted-c`
against it ([run.py:175-183,190-245](../2026_10_09_position_error_iter105/run.py)).
The three start names, 20-second and 600-iteration limits, position bounds,
`±60 Hz/s` slope bound, observations, prior, associated satellite bank, and
calibration are common to the two arms in that region. The `zero-c` fit locks
vector element 6 to zero ([regional_position_fit.py:81-85](../../src/leo/analysis/regional_position_fit.py)); the existing recovery also asserts
this ([run.py:228-245](../2026_10_09_position_error_iter105/run.py)).
The `own-continuation` start is intentionally arm-specific, so identical start
*names and budgets* do not imply identical seed vectors. Report effective seed
identity separately for each named start. The primary controlled comparison
uses only `association` and `zero-timing`, where effective seeds must match.
Treat `own-continuation` as a separate same-model, arm-specific-start
diagnostic, never pool it into the primary identical-seed estimate.

The exact diagnostic pair is `(member label, discovery branch, retained basin,
start name)`: one `zero-c` and one `fitted-c` B1 final from the **same raw
region receipt**. There are at most `193 × 2 × 3 × 3 = 3474` such pairs:
2316 primary identical-seed opportunities and 1158 arm-specific-continuation
opportunities. These are expected-opportunity counts, not assumed completed
pairs. A complete search followed by a failed continuation contributes zero
completed pairs and an explicit failure. For every opportunity, record both fit statuses,
qualification/convergence, failure reasons, stationarity, satellite numbers,
calibration identity/penalty, objective, posterior RMS, signal-window mass,
and effective seed identity. Assert equal satellite-number sequences and a
shared region calibration, observation binding, prior, score, local bounds, and
declared per-start budget before calling a pair **same-model**. A mismatch is
reported as an integrity failure, never silently paired or repaired. Keep
nonconverged and missing attempts in coverage; compute paired deltas only when
both endpoints exist and independently qualify. Do not substitute another
start, basin, branch, or selected operational endpoint.

After the full seal, evaluate reference position error for each qualified
same-model pair. Report `fitted-c minus zero-c` error in km, paired improvements,
regressions and missingness by dataset and branch. Treat the repeated basins
and starts from one recording as correlated diagnostic attempts; report member
counts separately and do not present the pooled attempt mean as a standalone
193-recording position mean. No basin or start is chosen with reference error.
For a per-recording B1 *policy* comparison, separately apply the existing
reference-free `regional_winners` rule to the same offered regional finals for
both arms, with its ordinary qualification and score tie-breakers
([hard60_b7.py:37-62](../../src/leo/application/hard60_b7.py)). Label this as
a matched **candidate-set** position comparison: its winning basin and bank
may differ, so do not call its winner objectives a same-model contrast.

Report objective and posterior-RMS changes only within exact same-region,
same-bank pairs, separately from position errors. The two values address
in-sample frequency fit and score, not geographic accuracy. Do not infer a
position gain from either value alone. Show qualified-pair coverage and the
failure denominator beside every summary; present full-member metrics only
when all required members are covered. Use the frozen source and raw-receipt
hashes from the iteration-164 evaluation gate, not a derived result file whose
provenance has not been checked.

## Limit of final operational `c` comparisons

Iteration 164's selected final endpoints are already reported as *policy
sensitivity*, not as a controlled same-model likelihood contrast
([report_metrics.py:126-133](report_metrics.py)). `regional_winners` can choose
different B1 regions for each arm. The later joint path takes the **fitted-c**
B1 winner as its seed, and its B4 bank pruning depends on the fitted-c B3 state
([hard60_b7.py:82-101,173-185](../../src/leo/application/hard60_b7.py)).
Subsequent accepted stages can also differ. Thus equal nominal arm budgets do
not make the final selected banks, candidate paths, or objectives identical.
The B1 diagnostic above does not cure that end-to-end confounding or establish
multiseparation deployed-B7 parity.

A later full-B7 `c`-isolation successor must be separately frozen before any
fits. Give both arms the same reference-free region opportunities, observation
and prior binding, per-region association/bank and model, stage list, start
policy, qualification/selection rule, and explicit equal budgets. Hold the
bank fixed through paired joint stages, or derive any common pruning mask from
a declared arm-neutral rule before either arm runs; do not let a fitted-c state
choose the zero-c bank or seed. Check each stage's physical model and bank
identity before comparing objectives. Keep arm-specific optimization states
and `c=0` projection, retain all failures, and report end-to-end geographic
accuracy separately from same-model frequency fit. A separate operational
policy comparison may permit distinct final winners if both arms see the same
candidate set; identical *winning* banks are required only for a direct
same-model objective comparison, not for that policy comparison. Use no
reference-guided seeds, region retention, satellite choice, per-scan tuning,
or winner selection; require new independent recordings before deployment
claims.
