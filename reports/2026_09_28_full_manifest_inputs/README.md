# Full-manifest input expansion for DS7, DS8 and DS9

This report tracks scientific input readiness for every published manifest
recording: **DS7 88, DS8 65, DS9 105**. It extends the successful 30-record model
panels toward complete datasets without outcome-based substitutions or silent
membership reduction. It is an input-preparation report, not a new localization
result. Previous sub-kilometre results and robustness checks remain in the
[combined-panel](../2026_09_28_combined30/README.md) and
[deletion-audit](../2026_09_28_block_deletion/README.md) reports.

The initial inventory found all 88 DS7 inputs cached, plus 30 DS8 and 30 DS9
inputs. The remaining 35 DS8 and 75 DS9 recordings require export of existing
cached frequency observations and candidate banks. All 258 captures are frozen
in [plan.json](plan.json), independent of cache availability or model outcome.

## Immutable readiness checkpoints

- [01: Reusable inputs](checkpoints/01-reuse/README.md): all 148 reusable inputs
  validated; complete DS7 ready, DS8 and DS9 still incomplete.
- Further completed checkpoints are retained under [checkpoints/](checkpoints/).
  Each has its own full ledger, readiness flags, resource receipts and hash
  inventory. Do not treat the existence of exported files as validation or
  combine partial groups into a purported full-dataset fit.

The main text describes the fixed workflow; readiness is explicitly versioned
in checkpoints so later additions do not rewrite earlier scientific evidence.

## Fixed workflow

[PROTOCOL.md](PROTOCOL.md) requires complete manifest membership, immutable
capture/pose/analysis bindings, existing loader eligibility gates and the
unchanged corrected-DS6 causal candidate bank. Provider snapshots must predate
capture by more than 505 seconds. DS9 also checks the minted GLRT metrics
manifest against exported observations. Track exclusions remain explicit;
recordings are never replaced based on fit outcome.

[prepare.py](prepare.py) verifies reusable artifact hashes and archives the
remaining DS7 cache banks byte-for-byte. [input-archive-map.json](input-archive-map.json)
records original and archived paths. Existing published paths are reused where
available. No saved waveforms are read, no radio collection occurs, no provider
is fetched, and QNAP paths remain read-only.

[launch.py](launch.py) runs one scientific process at a time with BLAS1/nice19
and a 4 GiB address-space cap. Each invocation has an 1,800-second deadline.
Observation exports are capped at 60 seconds, bank exports at 240 seconds and
validation at 30 seconds. Missing inputs use fixed chronological five-record
batches. No automatic scientific retries occur; completed receipts are verified
before skipping an already finished stage, while failures remain failures.

Available memory was constrained by independently running production tracking
jobs when this expansion began. The launcher therefore requires Linux
MemAvailable of at least 1 GiB for validation, 1.5 GiB for observations and
2 GiB for banks before starting each stage. Earlier measured RSS peaks were
160,132/405,916/891,688 KiB respectively. Low headroom leaves a stage unstarted
with an explicit worker receipt. No production jobs or services are modified.
These thresholds are headroom checks, not reservations against other workloads.

## Execution and audit

Use `launch.py reused` for reusable input validation, or `launch.py DS8 N` /
`launch.py DS9 N` for zero-based missing-input batch N. A file lock prevents
concurrent launchers in this report. Explicit continuation can resume a stage
that never started, without rerunning successful scientific stages.

After an invocation is terminal, `audit.py CHECKPOINT_NAME` verifies all current
stage seals, exact identities and manifest bindings, then writes a new immutable
checkpoint. It refuses an audit with an incomplete stage receipt. Only a group
whose validated count equals its complete manifest count receives a ready
full-dataset input list. Existing [tests.log](tests.log) records the partition
test; runtime versions and installed reader source snapshots are archived in
[environment.json](environment.json) and `runtime-sources/`.

Scientific results, logs, commands, exit codes and resource measurements remain
under `receipts/` and `validated/`. Worker status files preserve invocation
outcomes, including headroom/deadline stops. Derived bank archives are published
in bounded batches with explicit bank inventories. Publication-time inventories
describe their exact snapshot; experiment-time stage seals remain unchanged.
