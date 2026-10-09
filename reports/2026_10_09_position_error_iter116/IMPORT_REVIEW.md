# Independent pre-recovery import review

Read-only source and saved-receipt review found no remaining blocker for the approved **pre-recovery queue-only** preparation. No recording reconstruction, propagation, objective evaluation, fitting, truth evaluation or protocol freeze was performed.

The saved bundle SHA256 is `ab1c2d6c374307cad67c4492175a9ff5913963fa3d0d1a24718510bfacfc044c`. Independently verified all400 payload digests, bootstrap/fit vector digests, physical fixed-position/slope/common/total-timing checks and ordered877-satellite identity. All seven recorded recovery-original fit digests match the imported original fit payloads. The five changed displayed scores are correctly treated as post-search presentation changes; none replaces the original endpoint in this queue experiment.

A saved-scalar-only replay of the production-equivalent40/20/10/5 km nearest-edge hierarchy with250 km radius and400-point budget exactly reproduces all400 coordinates, spacings, scores and evaluation order. This checks queue provenance without calling an orbit or fit model.

Runtime admission checks bind the imported bundle, member, reconstructed observations/bank/prior and source closure. Old physical predictions and native objective must reproduce before whole-bank rescoring; no post-recovery endpoint alias is permitted. Failed source entries remain failures, and failure-influenced search outputs cannot become a complete result. The native baseline gate uses the restored pre-recovery trace. Final operational recovery/calibration/association/winner selection is outside this experiment.

The README correctly discloses unequal historical versus fresh computation: imported fitted-c endpoints reuse prior work, while c=0 fits are fresh under matched per-point limits and archived shared bootstrap starts. This is a conditional matched-model ablation, not four fresh equal-time searches. New-coordinate fits follow ordinary policy. No per-point reference error chooses an import, seed, bank or score.

The full synthetic suite passes35 tests on the exact production47e Python. Full reconstructed array preflight and a reviewed frozen executable protocol remain outstanding; metadata/source preparation does not authorize bypassing either gate or launching while numerical slots are occupied.
