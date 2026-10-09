# Historical numerical-source mismatch review

Read-only provenance/source inspection. No fits or objective evaluations performed.

The source plan identifies46 mismatched regional documents, all DS16 baseline
documents, with two numerical source hashes differing from current. They are not
444 independent numerical mismatches; other sources primarily have the separately
documented presentation-module mismatch.

| File | Historical SHA256 | Matching historical commit |
|---|---|---|
| analysis/regional_position_fit.py | c5aba169beafad93c11f707bf57ee2b72b7c343660be2f5d6943a22baead2ab8 |967566245 |
| application/hard60_runner.py |81ffd3839bf71d17ef2eb3425c0a16b876480850709a7306656e6f6361d5b5e9 |967566245 |

`git show 7d296d36d733a18fbc4ec28c63dc579ef2f7f136 --` these two files
isolates the changes (2026-10-08 14:39 UTC, “Recover failed Hard60 coarse fits
with directly bounded satellite timing”). Current hashes are respectively
15bc0a33acc9e747ee0c8be9d3b45301d1689d4af60421310a7f805d9907dbb2 and
aeb7ba28159be8687aefb28b710ffbe60bd0318d8a36b2cbc305bba9e50a3536.

## What changed

The fitter change factors the same first-order KKT calculation into an audit
helper, adds optional optimizer terminal/returned diagnostics, and makes the stop
reason identify solver-success/returned-state-nonstationarity. The best feasible
returned state's numerical qualification threshold remains0.001. When diagnostics
are requested, an additional terminal objective/gradient evaluation occurs after
optimization. This appears diagnostic, but that is a specific source finding, not
a blanket source-hash waiver.

The runner change **is operationally substantive**: it adds default
`recovery_policy="failed-coarse-box-v1"`, imports bounded coarse recovery, collects
optimizer diagnostics and invokes recovery before returning regional candidates.
The inspected historical run configuration has no recovery_policy field. Therefore
configuration/checkpoint key identity and the available candidate inventory differ
from today's ordinary Hard60/B7 pipeline. Even an identical Gaussian fit objective
does not prove an identical search/recovery policy or regional winner.

## Safe evaluation decision

Require a freshly reproduced **current-policy ordinary B7 baseline** for these
members before treating the candidate comparison as standard-pipeline recovery.
Reproduce all three regional passes, current existing coarse recovery and B7 joint
stages. Preserve historical outputs as provenance; do not alias old completed
regional/calibration/final/recovery receipts into current configuration keys.

An optional coarse-point-only compatibility adapter could reuse historical
bootstrap/coarse states after an explicit code-specific equivalence review,
input/analysis/evidence/prior/bank verification and independently recomputed saved
objective. It must account for missing diagnostics and the changed configuration
key, then execute all new current recovery stages. This is a separately reviewed
optimization, not permitted by the existing105 exact-current-source alias rule.
Without that adapter, recomputation is the truthful conservative default.

Do not waive hard60_runner.py alongside the presentation-only renderer. Existing
sep25/sep50 sources that independently match current policy can be reused under
their verified identities; mismatch in one baseline source does not contaminate
every other source. Record exactly which pass was recomputed, costs, failures and
baseline parity limits. Missing bindings and budget-exhausted members remain in
coverage. Known/reference positions may evaluate terminal results only.
