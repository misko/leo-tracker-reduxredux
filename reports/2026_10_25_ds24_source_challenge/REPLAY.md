# Replay and artifact map

This report combines two bounded research branches and a metadata-only inventory.
The operational reference, accepted observations and positions are unchanged.
No new RF collection, IQ extraction, GPS-based design or position fit occurs.
Source files retain their original absolute research dependencies; publication
does not copy the old radio corpus or rewrite frozen scientific code.

## Original environment

Run from `/home/mouse9911/gits/leo-tracker-reduxredux` with its `.venv/bin/python -B`.
The research SciPy environment is `/tmp/algo03-feasible-deps`. Set
`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1` and
`PYTHONDONTWRITEBYTECODE=1`. The common `PYTHONPATH` is
`/tmp/algo03-feasible-deps:src:tools:/srv/bulk/leo/research/ds24-movement-policy-r01/recovery`,
with the branch's original absolute directory appended.

Persisted JSON hashes bind the actual old source/input bytes. Replaying numerical
science requires those original dependencies and must use a fresh, explicitly
reviewed output location. The archived entry points refuse to overwrite outputs.
Passing tests or reproducing a coarse score does not authenticate an association.

## All frozen portions and whole-source control

Source: [portions/nominate.py](portions/nominate.py),
[owned tests](portions/test_nominate.py), [protocol prose](portions/PROTOCOL.md),
[frozen protocol](portions/protocol.json) and
[actual both-arm load smoke](portions/load_smoke.json).
The frozen protocol SHA256 is
`4495936258f5ce70de5918a13565cf93380da5de3f1966c5a3dce1f54cd0670c`.

The `prepare` stage verifies all43 original CH4 IDs, native/graph CFO gauge,
arm backgrounds, common saved c0 RF position and complete1487-entry causal
catalogue. It reconstructs only RF-blind per-ID mean elevations and verifies
the original nominal frequency cache exactly. It does not screen CFO.
Nine owned tests precede `freeze`; the matching
[independent preflight](audit/preflight.json) authorizes `run`.

`run` performs all six index-frozen portions and the whole-W control in both
arms,14 screens, with no candidate reserve or new cavity. Original coarse
aliases and Gaussian-affine phase proposals remain unbounded, with operational
domain flags exported separately. The six overlapping portions are not
independent factors. The exact inputs and full source-ID ledger are retained
under `portions/inputs/`.

Terminal evidence: [RF seal](portions/RF_seal.json),
[execution accounting](portions/execution.json) and
[independent176-check audit](audit/portions_terminal.json).
The cumulative numerical cost is4.439709447771 seconds including preparation
and owned tests, below180 seconds. All14 screens completed.

To rerun the owned tests without changing caches, append the original
`/srv/bulk/leo/research/ds24-source-challenge-r01/portions` directory to
`PYTHONPATH`, then run `.venv/bin/python -B -m pytest -q -p no:cacheprovider`
with the absolute path to `portions/test_nominate.py`.

[portions/report.py](portions/report.py) verifies scientific hashes and emits
only saved-result tables and plots into a fresh report directory. It performs
no orbit propagation, new score or fit. Main outputs are
[FINDINGS](portions/FINDINGS.md),
[all14 contexts](portions/report/contexts.csv),
[112 top8 proposal rows](portions/report/top8_proposals.csv),
[20,818 full-catalogue rows](portions/report/catalogue_scores.csv),
[2,752 native-CFO overlays](portions/report/native_CFO_overlays.csv) and
[report seal](portions/report/report_seal.json).

## Matched conditional-law controls

Source preparation is [matched_law/control.py](matched_law/control.py),
[law_math.py](matched_law/law_math.py),
[owned tests](matched_law/test_control.py) and
[protocol prose](matched_law/PROTOCOL.md). Its `prepare` stage freezes the
response-free source layouts, confusable generating family choices, seed,
backgrounds, prior/support/alias laws and input/source hashes before new draws.
The nominal panel has four physical and two unresolved observations, each
scored in both arms. Complete outputs, failures and numerical qualification
remain the authority; the panel is not expanded to replace difficult cases.

The c0 exogenous Gaussian background is common to generation and c0 scoring,
without a response-selected shortlist cavity. Fitted c scores the identical
observations as an off-law sensitivity. This is a conditional law control,
not full pipeline, shared-parent or IQ/GLRT generative calibration. Ordinary
nomination never receives the generating identity, source kind or a reserve.
A label-available diagnostic can expose a shortlist miss but cannot backfill it.

Append the branch's original absolute directory to `PYTHONPATH`; tests use
`.venv/bin/python -B -m pytest -q -p no:cacheprovider` and the absolute path to
`matched_law/test_control.py`. `control.py prepare` and `control.py run` refuse
to overwrite outputs, require bound inputs/preflight, and retain all failed
slots within the600 cumulative worker-second cap. The final
[branch protocol](matched_law/protocol.json), [RF seal](matched_law/RF_seal.json),
[191-check terminal audit](audit/matched_law_terminal.json),
[findings](matched_law/FINDINGS.md) and [saved-only report seal](matched_law/report/seal.json)
are checked before combined staging. All six observations/twelve arm-trial
slots completed in327.906501 cumulative worker-seconds, including preparation
and tests. The c0 physical labels all reached rank1 in nomination; two0010
physical orders are proved, two0011 physical orders remain numerically
overlapping, and both deliberately close null draws prefer physical models.
These are finite-model outcomes, not an operational false-association rate.

## Metadata inventory and publication

[metadata_inventory.py](metadata_inventory.py) reads existing exports and
authority schemas only. [Inventory](metadata_inventory.json) and
[METADATA_FINDINGS](METADATA_FINDINGS.md) preserve exact field counts/source
hashes and explain the corrected dictionary key-counting preparation error.
No observation or scientific input was changed by that repair. Detector epoch
offsets/scores alone are not calibrated timing, power or bearing observables.

[stage_publication.py](stage_publication.py) copies exact report bytes only after
both RF seals and independent terminal receipts exist and root narrative is
ready. It excludes caches, its own staging tree and publication receipts,
verifies every copied hash and local/cross-report Markdown link, and emits
`publication_manifest.json` plus staging checks. It does not fit, infer, write
the git checkout or push. Root reviews staging before the authorized final
publication into `reports/2026_10_25_ds24_source_challenge`; previous reports and
the dirty development worktree remain untouched.
