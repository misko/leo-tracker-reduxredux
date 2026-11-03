# DS7 parallel evaluation plan

Status: Wave 1 launched on 2026-09-27 after user authorization; see the [launch record](../../reports/2026_09_27_ds7_wave1/LAUNCH.md). This plan coordinates bounded evaluation of the frozen DS7 corpus. It does not authorize new RF collection, mutation of source captures, or a long-running campaign.

The authorized SOL/Terra continuation is documented in the [wave-2 launch](../../reports/2026_09_27_ds7_wave2/LAUNCH.md) and [executed comparisons](../../reports/2026_09_27_ds7_wave2/RESULTS.md). Those receipts distinguish positioning runs, diagnostic prerequisite tests, and model directions that remain gated.

## Decision this evaluation must support

DS7 should first determine whether the corrected DS6 joint static-site Doppler result transfers, how much recorded support it needs, and which physical correction is worth carrying into the next frozen model. The six directions are intentionally unequal: baseline and orbit-input results are gates for the more flexible models. A smaller residual is not success unless geographic error, availability, and failure behavior improve under the same evaluation contract.

The primary comparison unit is each of the eleven frozen chronological groups of eight recordings. The 88 single-recording units measure availability and failure tails; the full-88 unit measures one long-duration static-site estimate. Fixed 1/2/4/8 prefixes within each eight-recording group provide the recording-budget curve. Both receivers and all correlated observations from a recording remain in the same unit.

DS7 is a transfer evaluation at one repeated site. Prior research exposure has not been audited, and the operator-supplied roof coordinate is not surveyed truth. Results therefore must not be described as an untouched holdout, independent-site validation, or demonstrated operational sub-kilometre performance.

## Shared run contract

Every agent starts from the sealed DS7 membership, frozen evaluation units, and a committed experiment specification. A run is admissible only when its receipt binds:

- the DS7 manifest and evaluation-unit digests;
- the exact session IDs and source-manifest digests loaded;
- code revision, dependency/runtime identity, agent direction, model/config digest, orbit-source digest, and candidate-bank digest;
- evaluation view, group or prefix identity, random seed, search bounds, compute budget, start/end times, and terminal status;
- estimates before truth reveal, convergence and boundary flags, abstentions, failures, latency, and resource accounting;
- the reference authority and evaluator version used only during scoring.

The loading layer must validate the frozen membership and source seals before presenting read-only recording handles. It must not construct private storage paths in analyzers. Derived artifacts and results go to a direction-specific run directory; source IQ, DS7 manifests, pose companions, and QNAP data remain read-only.

Inference and evaluation are separate phases. During inference, the model adapter receives a generated reference-free plan and frozen inputs and may write only predictions and diagnostic evidence. The dataset verifier reads pose files to validate mint integrity, but only the evaluator uses their coordinates to score predictions. This is **interface separation, not filesystem sandbox isolation or proof of scientific independence**: the shared workspace, earlier reports, and operator coordinate may remain accessible to researchers and agents. Each report must preserve that distinction.

All directions use the same primary outputs: median, p90 and p95 horizontal error; fraction below 1 km; maximum error; availability and abstentions; convergence and boundary rates; initialization sensitivity; elapsed data support; wall time and peak resource use. Also report per-unit errors and every failure. RMS, likelihood, or held-frequency prediction are diagnostics rather than substitutes for location error. Uncertainty-bearing models additionally report interval coverage and calibration.

## Fixed scope and budgets

The initial launch uses existing derived products wherever possible. It may read the existing on-disk corpus and run bounded re-analysis, but it performs no RF collection and no multi-hour open-ended search. Before execution, the coordinator records concrete adapter-execution, CPU, memory, process-count, and IQ-byte limits in each experiment specification. The CLI enforces per-unit and whole-run adapter execution limits; input validation and hashing happen outside that timer. A worker stops at the first applicable limit and returns a valid partial receipt rather than quietly widening the budget.

Use this common progression:

1. **Transport smoke:** the `smoke` suite's first single recording, one fixed seed, and the smallest complete search budget. This validates loading, interface separation, adapter transport, output schemas, and deterministic replay.
2. **Scientific smoke:** select `single-001`, `prefix2-01`, `prefix4-01`, and `group8-01` from the `budgets` suite. This is the first 1/2/4/8 recording-budget comparison.
3. **Group evaluation:** all eleven groups of eight and their fixed prefixes. Run all 88 singles only where the method claims single-recording support.
4. **Full corpus:** one full-88 estimate only after the group gate passes. This is a pooled-site result, not 88 independent trials.
5. **Confirmation:** rerun only the selected, already-frozen contender with additional seeds or wider basins declared in advance. Do not tune on reference-scored DS7 outcomes and call the rerun confirmation.

For smoke runs, fail closed on a dataset/config digest mismatch, reference access during inference, missing receipt, non-finite estimate, or result overwrite. For expansion, require 100% planned-unit accounting, reproducible replay of the smoke result within declared numerical tolerance, no unexplained source or candidate changes, and no unresolved boundary/convergence defect.

## Directions and gates

### A. Corrected baseline and aggregation controls

Owner: baseline agent. Reproduce the corrected joint static-site Doppler solver using frozen causal element selection, stationary offset profiling, candidate policy, search limits, and numerical evaluation. Run independent fits plus equal averaging, inverse-RMS-squared averaging, lowest-RMS 75% averaging, joint prefixes, eleven groups, and full-88.

This direction is the scientific and operational reference. It advances when the smoke result is deterministic, all controls share identical input observations, failures are retained, and the DS6 behavior is reproduced closely enough to explain any implementation delta. All other agents consume its frozen observation/candidate products rather than independently changing preprocessing.

Stop if the corrected baseline cannot be reconstructed, if source/candidate identity changes across controls, or if scoring leaks into selection. A failed transfer is still a complete result and must be published as such.

### B. Causal orbit-input comparison

Owner: orbit-input agent. Hold observations, identities, nuisance model, search, and compute budget fixed while comparing available correctly dated orbit products. At minimum include the baseline causal GP product and zero-change control; add SupGP or provider ephemerides only when their archived, time-causal bytes and identifiers are available for the evaluated epochs.

Gate from A: the baseline observation and candidate digests are frozen. Advance an orbit source only if catalogue coverage and time causality are explicit, identifier/frame/time conversions pass checks, and the matched group results improve without reduced availability or a new failure tail.

Stop an unavailable product rather than substituting a current or retrospective file. Never present element download time, fit residual, or provider label as orbit truth.

### C. Constrained receiver-clock states

Owner: receiver-clock agent. Add only predeclared receiver-wide frequency, sample-clock, or timestamp states with physical sharing across the appropriate observations. Include zero-correction and injected-known-error recovery controls. Host timestamp brackets alone do not qualify as UTC calibration, and a stable SDR oscillator does not establish LNB stability.

Gate from A: matched baseline inputs and residual exports exist. Advance only when injected errors are recovered within declared tolerance, nuisance parameters are identifiable under prior/constraint removal checks, and held-group location improves rather than merely lowering frequency residuals.

Stop when clock states absorb the position derivative, become prior-boundary solutions, or lack an independently defensible constraint.

### D. Constrained satellite orbit-error hierarchy

Owner: orbit-hierarchy agent. Test shared per-satellite correction states with an explicit zero-correction arm, fixed identities or a separately frozen association bank, and priors learned without reference-scored target groups. First produce a repeated-satellite support audit; DS6 had no qualifying slope-transfer targets, so DS7 support cannot be assumed.

Gate from A and B: the selected orbit-input baseline is frozen. Advance only if enough repeated-satellite support exists for the declared hierarchy, position/orbit identifiability diagnostics pass, and improvement survives whole-group evaluation. Report unsupported groups as not estimable.

Stop if priors or corrections are tuned against target-group reference errors, donor/target separation is violated, identity conditioning is hidden, support is insufficient, or free corrections collapse geographic information. Estimating constrained latent correction states from target observations is allowed when that inference rule and its independent priors were frozen in advance.

### E. Association and geographic search

Owner: association/search agent. Test candidate completeness, multi-basin regional search, source/null alternatives, alias accounting, and wrong-association controls. Keep measurement extraction and physical model fixed. Compare inherited shortlist, independently regenerated catalogue bank, and explicit null/outlier support at matched compute budgets.

Gate from A: baseline candidate and score interfaces are frozen. Advance only if known injected/wrong-association controls behave correctly, final estimates are interior and converged, and catastrophic-error or abstention behavior improves without truth-directed shortlist selection.

Stop on unchecked catalogue gaps, silent hypothesis-cap truncation, edge winners, or search-budget comparisons that evaluate different observation sets.

### F. Improved pilot/CFO extraction

Owner: CFO agent. Start with a small frozen IQ panel chosen before scoring to span sample rates, strong/weak support, successful/failed tracking, and both receivers. Compare the baseline extractor with eligible known-pilot and full-/partial-frame alternatives at matched epochs. Preserve code/carrier divergence, discontinuity alternatives, false support, and runtime.

Gate from A: downstream baseline accepts a versioned observation product. Expansion beyond the panel requires improved held-window frequency prediction **and** better downstream group positioning or availability without excess false support. Native bandwidth and waveform assumptions must be declared per recording.

Stop if the method needs signal content absent from the recording, improves only its own fit residual, silently discards weak cases, or would require fresh RF. Full-corpus IQ reprocessing needs a separately declared bounded budget after the panel gate.

## Parallel launch schedule

There are four agent slots including the coordinator, so at most three SOL workers run concurrently. The coordinator owns contracts, frozen specs, resource leases, scoring, integration, and the decision log; workers own only their direction-specific implementation and result directory. A worker may not spawn further agents.

| Wave | Concurrent SOL workers | Dependency and deliverable |
|---|---|---|
| 0 | Coordinator only | Verify DS7 seals; freeze schemas, baseline config, truth-access boundary, resource limits, output roots, and smoke unit. No scientific run starts here. |
| 1 | A baseline; B orbit inventory/adapters; F CFO panel/adapters | A runs the decisive smoke. B and F may inventory inputs and run unit/synthetic checks, but cannot score DS7 variants until A freezes matched products. |
| 2 | B orbit comparison; C receiver clocks; E association/search | Three matched smoke evaluations. C and E consume A outputs. B publishes coverage/causality evidence with results. |
| 3 | D orbit hierarchy; best surviving arm from Wave 2; F CFO panel | D starts only after A/B freeze the orbit baseline. The second slot expands one evidence-backed contender; F remains panel-bounded. |
| 4 | Up to three surviving directions | Eleven-group evaluation. Allocate one CPU/I/O lease per worker and serialize IQ-heavy work against other bulk readers. |
| 5 | Coordinator plus at most two confirmation workers | Full-88 for gated contenders, reproducibility reruns, blinded scoring, comparison table, and limitations. |

Resource coordination is explicit. The coordinator maintains a lease record for CPU cores, memory, bulk-I/O class, result path, and expected deadline. These CPU, memory, and IQ-I/O leases are coordination policy, not enforcement implemented by the CLI. At most one IQ-heavy worker reads adaptive-hop payloads at a time; metadata and cached-observation work may overlap. The runner restricts BLAS thread variables to one and caps child-created regular files at 16 MiB. Result paths are unique and immutable after terminal receipt. A crashed or capped worker releases its lease only after writing terminal state; the coordinator can then retry with a new run ID, never overwrite the first run.

### Coordinator command sequence

The checked-in `tools/ds7_eval.py` command is the shared control plane. It prepares and seals requests; a model arm remains an external adapter invoked with appended `--request PATH --response PATH` arguments. Preparing infrastructure does not imply that any arm exists or has run.

Set these paths explicitly in each launch record (the examples use repository-relative paths only for readability):

```sh
python3 tools/ds7_eval.py inspect \
  --dataset reports/2026_09_27_ds7_post_ds6

python3 tools/ds7_eval.py prepare \
  --dataset reports/2026_09_27_ds7_post_ds6 \
  --output runs/ds7/plans/smoke \
  --suite smoke

python3 tools/ds7_eval.py freeze-inputs \
  --plan runs/ds7/plans/smoke/plan.json \
  --index runs/ds7/input-indexes/baseline.json \
  --output runs/ds7/inputs/baseline.json

python3 tools/ds7_eval.py run \
  --plan runs/ds7/plans/smoke/plan.json \
  --inputs runs/ds7/inputs/baseline.json \
  --arm config/ds7/baseline.json \
  --output runs/ds7/predictions/baseline-smoke \
  --max-seconds 300 \
  --unit-seconds 60

python3 tools/ds7_eval.py evaluate \
  --dataset reports/2026_09_27_ds7_post_ds6 \
  --run runs/ds7/predictions/baseline-smoke \
  --output runs/ds7/scores/baseline-smoke
```

Before `freeze-inputs`, copy the generated `inputs.template.json` to the direction-specific index shown above, set `reference_audit` to `reference_excluded`, and populate each ready session's artifact references; unavailable sessions retain an explicit reason. An input index is not permission to trigger production analysis or IQ extraction. `run` produces sealed, reference-free per-unit predictions with one of `ok`, `abstained`, `failed`, or `unavailable`; successful estimates also report convergence and boundary state. `evaluate` is the only command that uses pose coordinates to score a sealed run, although dataset verification reads pose artifacts to validate integrity.

The `smoke` suite contains only `single-001`. The `standard` suite contains 100 units: 88 singles, eleven groups of eight, and `full88`. The `budgets` suite contains those 100 plus eleven two-recording and eleven four-recording prefixes, for 122 units. After the transport smoke, prepare `--suite budgets` and run the first scientific panel with repeated selectors:

```sh
python3 tools/ds7_eval.py run \
  --plan runs/ds7/plans/budgets/plan.json \
  --inputs runs/ds7/inputs/baseline.json \
  --arm config/ds7/baseline.json \
  --output runs/ds7/predictions/baseline-budget-smoke \
  --max-seconds 300 \
  --unit-seconds 60 \
  --unit single-001 \
  --unit prefix2-01 \
  --unit prefix4-01 \
  --unit group8-01
```

These limits cap child adapter execution, not total command wall time. The runner permits at most 1,800 seconds, and future sharding is required before a large campaign. Each new suite and arm gets a new output path. Never reuse an output directory to rerun or repair a result. The six planned direction files are `baseline.json`, `orbit-inputs.json`, `receiver-clock.json`, `orbit-hierarchy.json`, `association.json`, and `cfo-extraction.json` under `config/ds7/`. These remain admission specifications. Executable arms are separately named `*-ready-v1.json`, including the corrected baseline and matched association searches prepared during the authorized wave. An arm configuration binds its model ID, argv, scientific configuration, and code paths. Consult the [wave results](../../reports/2026_09_27_ds7_wave1/RESULTS.md) for actual runs and current gates.

The coordinator launches collaboration agents with `model="gpt-5.6-sol"` and `fork_turns="none"`, at most three at once. Each receives the common work package, exact repository and generated reference-free artifact paths, direction section, resource lease, and frozen run IDs in its prompt. This reduces accidental cross-arm leakage while leaving all scientific-independence limitations above in force. The coordinator, rather than a worker, runs `evaluate` after receiving the sealed prediction directory.

## SOL-agent work package

Each agent receives the same short preamble plus one direction section above:

> Work only on direction `<id>` against frozen DS7. Read `AGENTS.md`, this plan, the evaluation-infrastructure guide, and the generated reference-free plan and inputs named below. Do not inspect the full DS7 manifest, pose artifacts, or reference coordinates during model work. Do not collect RF, mutate source data, change frozen membership, expand compute limits, or spawn agents. Use the shared loader/runner/result schemas and direction-specific output root. First produce a sealed arm specification and transport smoke result. Preserve failures and write a terminal receipt even when blocked. Report code changes, exact commands, artifact digests, scientific results, limitations, and whether every gate passed. Do not claim an untouched holdout or independent-site validation.

Agents submit implementation and evidence, not a prose-only success claim. The coordinator rejects results without the shared receipt, exact unit accounting, reproducible command, and reference-free prediction artifact.

## Coordinator launch checklist

Before Wave 1, the coordinator must be able to answer yes to all of the following:

- DS7 offline verification passes and the loader reports 88 exact members and eleven groups of eight.
- The experiment spec and result schemas have stable version identifiers and tests.
- Model requests contain no pose coordinates or pose artifacts; scoring is a separate command. Dataset verification may read pose files only to validate mint integrity.
- The baseline config, smoke unit, seeds, search bounds, numerical tolerance, and resource limits are sealed.
- Result directories are unique, refuse overwrite, and retain partial/failed runs.
- CPU, memory, and bulk-I/O leases prevent more than three workers and more than one IQ-heavy reader.
- Every proposed external orbit product is archived and causal for its target epoch, or is marked unavailable.
- No command starts capture hardware, mutates QNAP, or creates a multi-hour unbounded process.

After each wave, update one decision table with gate evidence: run/spec digests, units attempted/completed, headline metrics, failures, resource use, and **advance / stop / repair**. Repair means an implementation defect can be corrected without looking at reference scores; scientific underperformance means stop, not post-hoc tuning. Launching a later wave requires the coordinator to record that decision explicitly.
