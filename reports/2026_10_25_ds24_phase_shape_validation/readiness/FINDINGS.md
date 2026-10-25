# Eight frozen later fast inputs are ready for the declared comparison

All8 predeclared cases pass full input-contract and raw-identity reconciliation.
No member was replaced. Validation used22.14s of input processing under the600s
cap, with one worker and one BLAS thread. There were no fits, IQ reads,
GLRT regeneration, new position/error lookups or dataset mutations.

The ready [sample.json](sample.json) is compatible with the existing
`tools/prepare_algo02_ds23.py` fast-input export. Its SHA256 is
`e4dbc7bee7647cf616d5966fcdf5a6a6f0a2cb844c865e3c28c2507c5f6b6155`.
The research labels RX1V-0001…0008 are not DS26 or a revised DS24 membership.
DS24-0103 and its authority mismatch were excluded from this panel from the start.

## Selection and actual input support

The [panel protocol](panel_protocol.json) was frozen before full validation,
using the first8 of29 saved complete+qualified10MSps metadata jobs. Selection
used only the saved chronological name-time proxy and status. Full validation
then verified canonical acquisition times and their unchanged ordering.
Every case starts after the prior exclusive cutoff2026-10-24T14:38:14Z.

| Research case | Canonical manifest capture UTC, October24 | Recorded windows | Declared excluded windows | Valid receiver/probe records |
| --- | --- | ---: | ---: | ---: |
| RX1V-0001 |15:22:09.106697 |6771 |26 |13490 |
| RX1V-0002 |16:32:25.654476 |6773 |2 |13542 |
| RX1V-0003 |17:22:39.673373 |6771 |5 |13532 |
| RX1V-0004 |18:32:55.679652 |6772 |1 |13542 |
| RX1V-0005 |19:23:09.564599 |6771 |0 |13542 |
| RX1V-0006 |20:13:23.574230 |6771 |1 |13540 |
| RX1V-0007 |21:03:37.621555 |6772 |0 |13544 |
| RX1V-0008 |21:53:51.779865 |6774 |0 |13548 |

All scans contain both receivers and channels1–8. Exclusions are the existing
published invalid-capture declarations; validation neither adds exclusions nor
filters cases by their count, observed CFO, candidate score or inferred position.
Every remaining window has exactly one complete probe per receiver. These are
input/probe counts, not accepted satellite associations or localized points.

## What was validated

[frozen_input_hashes.json](frozen_input_hashes.json) records the complete tracking
document SHA256 values before typed validation. The public `FastScanStore`
read ports bind each run to its exact source session and recording name, with
canonical source-inventory digest verification. The deployed public
`TrackingInput` contract validates all nested probes/candidates. Explicit checks
add finite numerical fields, native-ID coordinates, receiver/window coverage,
unchanged fractional-margin flags, source counters, configuration consistency
and full source-document rehashing after validation.

The public `ShortWindowReader` constructor validates only manifests. Typed
native index records and their complete byte hashes are checked against those
manifests. Ordered window content hashes reconstruct the published raw authority
`canonical_digest([input_manifest_digest, ordered_IQ_hashes])` exactly for all8.
The old inventory's content identity, derived from sorted compressed/index
digest pairs, is also saved independently of directory names. IQ payloads are
never opened or decompressed; their actual bytes are not newly rehashed.

The analysis-manifest digest is bound as declared in the published tracking
document; upstream GLRT analysis artifacts were not independently reloaded.
This is full validation of the existing public input and its manifest/index
authority, not an independent rerun of the detector. The fixed new contract
hashes are the scientific-input authorities for the later fit stage.

The two public contract packages have different checkout layouts: the deployed
checkout contains `TrackingInput`, while the current checkout contains the
native multirate index contract. An initial import failed before input
processing. The final implementation isolates the deployed contract validator
in a separate subprocess, bound to the identical full input SHA, and uses the
current public native storage/index ports for raw validation. It does not mix
incompatible module contexts or fall back to an unvalidated parser. Both source
locations and hashes are recorded. No input failure or replacement resulted.

A supplementary configuration comparison initially looked for the older
sample's `raw_recording` envelope and stopped with `KeyError`; that compact
sample instead supplies `raw_manifest_receipts`. The corrected comparison uses
those explicitly provided receipt paths and verifies their hashes. The selected
eight inputs, source identities and main validation were not changed. These
setup-only false starts are recorded in [preparation_notes.json](preparation_notes.json).

## Geographic exposure and site assumption

Exact recording/session/raw identities have zero matches in the frozen
DS24/DS25 analysis sample or its prior position-table identity columns. Outcome
values were neither inspected nor used. The published repository search at
`5217788f231f9edce40ddca515a636a26bb97659` finds only three matching files:

- Prior identity-components `audit/exposure_inventory.json` (superseded metadata).
- Its corrected `audit/exposure_inventory02.json`.
- Its `audit/exposure_metadata.csv`.

All three are metadata-only exposure. The search covers tracked report
JSON/CSV/Markdown, not every compressed release, private notebook or person's
inspection history. Accordingly this is a chronological later panel with no
known prior research outcome exposure in the checked authorities; it is not
proof of an entirely untouched geographic benchmark. Production position-stage
completion is separately recorded and does not prove geographic-error exposure.
[exposure_matches.json](exposure_matches.json) binds the exact lookup scope.

[station_configuration_check.json](station_configuration_check.json) confirms
the same radio serial and the exact same two upper/lower capture-configuration
digest families as frozen DS24-0099/0101. The checked public contracts contain
no capture-bound station, deployment, pose or mount identifier. Thus matching
hardware/configuration supports continuity of capture setup, but cannot prove
no relocation. Any later same-site geographic evaluation must retain that
assumption explicitly rather than treating this metadata as an independent
position certificate. No production position was retrieved to establish it.

## Exact entry points and dependencies

Readiness was executed from the current repository with:

```sh
sudo -n env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/mouse9911/gits/leo-tracker-reduxredux/src /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -B /srv/bulk/leo/research/ds24-phase-shape-validation-r01/readiness/validate_panel.py
```

It invokes [validate_tracking_contract.py](validate_tracking_contract.py) with
`PYTHONPATH=/home/mouse9911/gits/leo-shared-production-main/src` for the deployed
typed contract only. Existing source inventories, raw manifests/index metadata
and published GLRT inputs need read access. Completed artifacts are preserved;
the script refuses to overwrite them. Reproduction needs a fresh output copy
and exact pinned inputs, rather than a rerun over changed live contracts.

For the later comparison, copy the exact frozen sample into the separate
`validation/` run root before its protocol/source freeze. The existing export
entry point is `tools/prepare_algo02_ds23.py --run-dir RUN_ROOT --case RX1V-0001
--stage export`; `--stage prepare` subsequently constructs the original graph,
noise and causal catalogue/history inputs. The root-owned supervisor is:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -B /srv/bulk/leo/research/ds24-phase-shape-validation-r01/validation/runner.py --stage run
```

That command requires its own frozen `validation/protocol.json` and matching
independent preflight receipt. It compares the existing fresh reference against
the unchanged RX1-rf50 source under matched c=0/fitted-c observations, candidates,
priors and budgets; no tuning follows from readiness. No fit command was run by
this readiness branch. Root controls launch, RF sealing and later geographic
evaluation. The original DS25 engine, receiver-control adapter, repository
research modules and existing causal TLE archive remain required dependencies;
this directory is not a standalone runtime or raw-IQ distribution.
