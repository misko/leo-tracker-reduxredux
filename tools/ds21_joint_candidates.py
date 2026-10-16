"""Protocol-gated singleton native-candidate inventory control; no RF collection."""

import argparse
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
from ds20_channel_corpus import ADAPTER, digest
from ds21_common import OUTPUT, immutable
from ds21_joint import objective as native_objective
from ds21_joint_proposals import run as run_proposals
from joint_association_candidates_native import POLICY, all_native_candidate_inputs
from joint_association_native import native_branch_inputs

from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.joint_association_candidates import NativeCandidateSingletonObjective
from leo.application.hard60_runner import HARD60_SCORE

VARIANTS = ("collapsed", "all-candidates")
FROZEN_FIELDS = dict(
    schema="ds21-native-candidate-control-v2", labels=["DS21-005", "DS21-023"],
    views=["all"], variants=list(VARIANTS), arms=["fitted-c", "zero-c"], starts=6,
    fit_seconds=20, iterations=600, local_radius_km=25, maximum_slice_seconds=500,
    maximum_new_fit_calls=36, maximum_total_fit_calls=48, carried_fit_calls=12,
    carried_condition=dict(label="DS21-005", variant="collapsed"), candidate_policy=POLICY,
    candidate_prior="1/(available cells * actual alternatives in this cell)",
    visibility_policy="mask after prior; preserve raw visible mass",
    waveform="neutral; no measured evidence", temporal_edges=0,
    physical_inputs="Original observations, satellite bank, saved seeds and applied lifts",
    held_comparison="common all-candidate scorer plus own scorer; no fitting or selection",
    reference_usage="none", held_selection="none",
    oracle_atol=1e-8, oracle_rtol=1e-11,
)


def scientific_sources():
    """Pin scientific modules and the exact loaded native binary before execution."""
    import ds21_common as common
    import ds21_shared_proposals as shared

    from leo.analysis import _regional_orbits

    root = Path(__file__).parents[1]
    names = (
        "tools/ds21_joint_candidates.py", "tools/ds21_joint.py",
        "tools/ds21_joint_proposals.py", "tools/joint_association_native.py",
        "tools/joint_association_candidates_native.py",
        "src/leo/analysis/joint_association_candidates.py",
        "src/leo/analysis/joint_association_graph.py",
        "src/leo/analysis/joint_association_score.py",
        "src/leo/analysis/joint_association_sparse.py",
        "src/leo/analysis/joint_association_projection.py",
        "src/leo/analysis/channel_group_calibration.py",
        "src/leo/analysis/frozen_group_calibration.py",
        "src/leo/analysis/regional_position_score.py",
        "src/leo/analysis/regional_position_fit.py", "src/leo/analysis/hard60_score.py",
        "src/leo/analysis/hard60_bounded_fit.py", "src/leo/analysis/_regional_orbits.cpp",
        "src/leo/analysis/research/doppler_shape_shared_proposals.py",
        "src/leo/analysis/starlink/fractional_epoch.py",
        "src/leo/analysis/starlink/templates.py", "src/leo/application/hard60_runner.py",
        "src/leo/application/scanner_trajectory.py",
        "src/leo/application/regional_position_inputs.py",
        "src/leo/application/channel_group_holdout.py",
        "src/leo/contracts/regional_position.py",
    )
    paths = {name: root / name for name in names}
    paths.update({
        "shared-tools/ds21_common.py": Path(common.__file__),
        "shared-tools/ds21_shared_proposals.py": Path(shared.__file__),
        "native-kernel/_regional_orbits.so": Path(_regional_orbits.__file__),
        "input-adapter/fast_scan_standard_pipeline.py": ADAPTER,
    })
    return paths


def loaded_scientific_dependencies():
    result = {}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if filename is None:
            continue
        path = Path(filename).resolve()
        if path.is_file() and ("/src/leo/" in str(path) or "/tools/" in str(path)):
            result[name] = dict(path=str(path), sha256=digest(path))
    result["pinned_input_adapter"] = dict(path=str(ADAPTER), sha256=digest(ADAPTER))
    return result


def loaded_source_hashes():
    return {row["path"]: row["sha256"] for row in loaded_scientific_dependencies().values()}


def study_directory(label, variant):
    return OUTPUT / "local" / f"joint-native-candidate-{variant}-v2" / label


def validate_archives(directory, protocol, *, require_mapping=False):
    """Historical archives bind old bytes; live files may legitimately have evolved."""
    mapping = protocol.get("source_snapshot_paths")
    if require_mapping and (mapping is None or set(mapping) != set(protocol["sources"])):
        raise ValueError("Archived source mapping differs")
    for filename, sha in protocol["sources"].items():
        relative = Path(mapping[filename] if mapping is not None else Path(filename).name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Archived source path is not local")
        archived = directory / "source-snapshot" / relative
        if not archived.is_file() or digest(archived) != sha:
            raise ValueError("Archived source is missing or corrupted")


def validate_frozen_protocol(path, label, variant, case):
    frozen = json.loads(Path(path).read_bytes())
    if any(frozen.get(key) != value for key, value in FROZEN_FIELDS.items()):
        raise ValueError("Coordinator protocol differs from the frozen candidate-control scope")
    if label not in frozen["labels"] or variant not in frozen["variants"]:
        raise ValueError("Case/variant outside coordinator protocol")
    if frozen.get("membership_sha256") != digest(OUTPUT / "membership.json"):
        raise ValueError("Candidate-control membership changed")
    paths = scientific_sources()
    if frozen.get("source_sha256") != {key: digest(p) for key, p in paths.items()}:
        raise ValueError("Candidate-control scientific source changed after freeze")
    closure = frozen["loaded_source_sha256"]
    if (any(closure.get(p) != sha for p, sha in loaded_source_hashes().items())
            or any(digest(Path(p)) != sha for p, sha in closure.items())):
        raise ValueError("Candidate-control loaded scientific closure changed after freeze")
    binding = frozen["cases"][label]
    if (
        binding["proposal_protocol_sha256"] != case["proposal_binding"]["protocol_sha256"]
        or binding["proposal_terminal_sha256"] != case["proposal_binding"]["terminal_sha256"]
        or binding["prepared_all_sha256"] != case["prepared"]["all"].evidence_sha256
        or binding["catalogue_numbers"] != case["bank"].numbers.tolist()
        or binding["input_sha256"] != case["member"]["input"]["sha256"]
    ):
        raise ValueError("Candidate-control observations/bank/common proposals changed")
    parent = Path(binding["native_parent_directory"])
    for key, name in (("bank_npz", "bank.npz"), ("bank_receipt", "bank.json")):
        bank_path = Path(binding[f"{key}_path"])
        if (bank_path != case["directory"] / name
                or digest(bank_path) != binding[f"{key}_sha256"]):
            raise ValueError("Original ephemeris bank/receipt changed")
    if json.loads(Path(binding["bank_receipt_path"]).read_bytes())["sha256"] != (
        binding["bank_npz_sha256"]
    ):
        raise ValueError("Original ephemeris receipt no longer binds the bank")
    protocol_path, terminal_path = parent / "protocol.json", parent / "terminal.json"
    if (digest(protocol_path) != binding["native_parent_protocol_sha256"]
            or digest(terminal_path) != binding["native_parent_terminal_sha256"]):
        raise ValueError("Original native seed parent changed")
    protocol, terminal = (json.loads(p.read_bytes()) for p in (protocol_path, terminal_path))
    identifiers = [row["id"] for row in case["proposal_seeds"]["all"]]
    if (terminal["protocol_sha256"] != digest(protocol_path)
            or protocol["proposal_binding"] != {
                key: str(value) for key, value in case["proposal_binding"].items()
            }
            or protocol["prepared"]["all"] != binding["prepared_all_sha256"]
            or protocol["catalogue_numbers"] != binding["catalogue_numbers"]
            or protocol["proposal_ids"] != identifiers
            or protocol["shared_discovery_sha256"] != case["protocol_sha256"]
            or any(protocol.get(k) != v for k, v in dict(
                fit_seconds=20, iterations=600, starts=6, c_arms=FROZEN_FIELDS["arms"],
                reference_usage="none", held_selection="none",
            ).items())):
        raise ValueError("Native parent objective/proposals differ")
    validate_archives(parent, protocol)
    expected = {f"all-{i}.json" for i in range(6)}
    if set(binding["seed_sha256"]) != expected:
        raise ValueError("Exactly six original saved seed hashes required")
    lifts_path = parent / "receiver-branch-starts.json"
    if digest(lifts_path) != binding["receiver_branch_starts_sha256"]:
        raise ValueError("Original receiver lift receipt changed")
    lifts = json.loads(lifts_path.read_bytes())
    if len(lifts) != 6:
        raise ValueError("Exactly six original receiver lift rows required")
    for index, identifier in enumerate(identifiers):
        seed_path = parent / "seeds" / f"all-{index}.json"
        if digest(seed_path) != binding["seed_sha256"][seed_path.name]:
            raise ValueError("Original saved seed changed")
        row = json.loads(seed_path.read_bytes())
        if (row["protocol_sha256"] != digest(protocol_path) or row["proposal_id"] != identifier
                or row["receiver_branch_lifts"] != lifts[index]):
            raise ValueError("Original saved seed binding differs")
    oracle_path = Path(frozen["oracle_receipt_path"])
    if digest(oracle_path) != frozen["oracle_receipt_sha256"]:
        raise ValueError("Collapsed oracle receipt changed")
    oracle = json.loads(oracle_path.read_bytes())
    replay = oracle.get("case_results", {})
    expected_states = {f"seed-{i}" for i in range(6)} | {
        f"{arm}-{i}" for arm in FROZEN_FIELDS["arms"] for i in range(6)
    }
    if (oracle["source_sha256"] != frozen["source_sha256"] or not oracle["passed"]
            or oracle["states"] != 36 or oracle["labels"] != frozen["labels"]
            or oracle["case_bindings"] != frozen["cases"]
            or oracle["loaded_source_sha256"] != closure
            or oracle["atol"] != frozen["oracle_atol"]
            or oracle["rtol"] != frozen["oracle_rtol"]
            or set(replay) != set(frozen["labels"])
            or any(len(rows) != 18 or {row["state"] for row in rows} != expected_states
                   or not all(row["passed"] for row in rows) for rows in replay.values())):
        raise ValueError("Collapsed oracle does not bind the frozen control")
    return frozen, paths, parent


def validate_terminal_structure(terminal, protocol, case, frozen, label, variant):
    binding = frozen["cases"][label]
    if (protocol["label"] != label or protocol["model"] != "C"
            or protocol["policy"] != f"joint-native-candidate-{variant}-v2"
            or protocol["proposal_binding"] != {
                key: str(value) for key, value in case["proposal_binding"].items()
            }
            or protocol["prepared"]["all"] != binding["prepared_all_sha256"]
            or protocol["catalogue_numbers"] != binding["catalogue_numbers"]
            or protocol["shared_discovery_sha256"] != case["protocol_sha256"]
            or protocol["scientific_control"]["parent_binding"] != binding
            or protocol["scientific_control"]["loaded_source_sha256"] != (
                frozen["loaded_source_sha256"]
            )
            or any(protocol.get(k) != v for k, v in dict(
                fit_seconds=20, iterations=600, starts=6, c_arms=FROZEN_FIELDS["arms"],
                reference_usage="none", held_selection="none",
            ).items())):
        raise ValueError("Sealed candidate-control inputs/parent/budgets differ")
    identifiers = [row["id"] for row in case["proposal_seeds"]["all"]]
    if protocol["proposal_ids"] != identifiers:
        raise ValueError("Sealed candidate-control proposals differ")
    result = terminal["results"]["all"]
    if (set(result.get("attempts", {})) != set(FROZEN_FIELDS["arms"])
            or set(result.get("selected", {})) != set(FROZEN_FIELDS["arms"])
            or terminal["proposal_binding"] != protocol["proposal_binding"]
            or terminal["reference_usage"] != "none"):
        raise ValueError("Sealed candidate-control requires all 12 attempts and selected arms")
    for arm in FROZEN_FIELDS["arms"]:
        rows = result["attempts"][arm]
        if (len(rows) != 6 or [row["start"] for row in rows] != list(range(6))
                or [row["proposal_id"] for row in rows] != identifiers
                or any("converged" not in row["fit"] for row in rows)):
            raise ValueError("Sealed candidate-control attempt inventory differs")
        selected = result["selected"][arm]
        eligible = [row for row in rows if row["fit"]["converged"]]
        if not eligible:
            if selected.get("state") != "unavailable":
                raise ValueError("Sealed candidate-control promotes a failed path")
            continue
        winner = min(eligible, key=lambda row: (row["fit"]["objective"], row["start"]))
        if (any(selected.get(key) != winner[key] for key in ("start", "proposal_id", "fit"))
                or set(selected.get("held_prediction", {})) != {
                    "own", "common_all_candidates", "comparison"
                }):
            raise ValueError("Sealed candidate-control selection/held scorer differs")


def checkpoint_inventory(binding):
    """Validate all old receipts, including failed outcomes with no state vector."""
    parent = Path(binding["directory"])
    protocol_path = parent / "protocol.json"
    if digest(protocol_path) != binding["protocol_sha256"]:
        raise ValueError("Carried candidate checkpoint protocol changed")
    protocol = json.loads(protocol_path.read_bytes())
    control = protocol["scientific_control"]
    if (control["frozen_protocol_sha256"] != binding["frozen_protocol_sha256"]
            or protocol["label"] != "DS21-005" or control["variant"] != "collapsed"
            or protocol["effective_views"] != ["all"]
            or protocol["policy"] != "joint-native-candidate-collapsed-v1"
            or len(protocol["proposal_ids"]) != 6
            or any(protocol[k] != v for k, v in dict(
                fit_seconds=20, iterations=600, starts=6, c_arms=FROZEN_FIELDS["arms"],
                reference_usage="none", held_selection="none",
            ).items())):
        raise ValueError("Carried checkpoint is outside the completed original condition")
    validate_archives(parent, protocol, require_mapping=True)
    seeds, attempts = {}, {}
    expected_seeds = {f"all-{i}.json" for i in range(6)}
    expected_attempts = {f"all-{i}-{arm}.json" for i in range(6) for arm in FROZEN_FIELDS["arms"]}
    if (set(binding["seed_sha256"]) != expected_seeds
            or set(binding["attempt_sha256"]) != expected_attempts):
        raise ValueError("Carried checkpoint requires exactly six seeds and twelve attempts")
    for kind, inventory, hashes in (("seeds", seeds, binding["seed_sha256"]),
                                     ("attempts", attempts, binding["attempt_sha256"])):
        for name, sha in hashes.items():
            path = parent / kind / name
            if digest(path) != sha:
                raise ValueError("Carried checkpoint bytes changed")
            row = json.loads(path.read_bytes())
            index = int(name.split("-")[1].split(".")[0])
            if (row["protocol_sha256"] != binding["protocol_sha256"]
                    or row["proposal_id"] != protocol["proposal_ids"][index]):
                raise ValueError("Carried checkpoint receipt protocol/proposal differs")
            if kind == "attempts" and (not isinstance(row.get("fit"), dict)
                                        or "converged" not in row["fit"]):
                raise ValueError("Carried checkpoint lacks its recorded fit outcome")
            inventory[name] = row
    return protocol, seeds, attempts


def validate_checkpoint_migration(directory, frozen, frozen_protocol):
    binding = frozen["checkpoint_parent"]
    old_protocol, seeds, attempts = checkpoint_inventory(binding)
    path = directory / "checkpoint-migration.json"
    if not path.is_file():
        raise ValueError("Complete checkpoint migration required before any optimizer call")
    migration = json.loads(path.read_bytes())
    protocol_sha = digest(directory / "protocol.json")
    if (migration.get("state") != "complete" or migration.get("optimizer_calls") != 0
            or migration.get("carried_fit_calls") != 12 or migration.get("parent") != binding
            or migration.get("new_protocol_sha256") != protocol_sha
            or migration.get("new_frozen_protocol_sha256") != digest(Path(frozen_protocol))):
        raise ValueError("Incomplete or rebound checkpoint migration")
    expected = {"protocol.json": binding["protocol_sha256"]}
    expected.update({f"seeds/{n}": s for n, s in binding["seed_sha256"].items()})
    expected.update({f"attempts/{n}": s for n, s in binding["attempt_sha256"].items()})
    if set(migration["active_sha256"]) != set(expected) - {"protocol.json"}:
        raise ValueError("Checkpoint migration active inventory is incomplete")
    for relative, sha in expected.items():
        if digest(directory / "checkpoint-parent" / relative) != sha:
            raise ValueError("Copied original checkpoint bytes differ")
        if relative == "protocol.json":
            continue
        active = directory / relative
        if digest(active) != migration["active_sha256"][relative]:
            raise ValueError("Active carried checkpoint wrapper changed")
        row = json.loads(active.read_bytes())
        original = (seeds if relative.startswith("seeds/") else attempts)[active.name]
        if (row["protocol_sha256"] != protocol_sha
                or row["proposal_id"] != original["proposal_id"]
                or (relative.startswith("seeds/") and any(row[k] != original[k]
                    for k in ("seed", "receiver_branch_lifts")))
                or (relative.startswith("attempts/") and row["fit"] != original["fit"])):
            raise ValueError("Carried fit/seed content differs from original bytes")
    new_protocol = json.loads((directory / "protocol.json").read_bytes())
    if any(new_protocol[k] != old_protocol[k] for k in (
        "label", "prepared", "catalogue_numbers", "proposal_ids", "proposal_binding",
        "shared_discovery_sha256", "fit_seconds", "iterations", "starts", "c_arms",
    )):
        raise ValueError("Checkpoint migration changed scientific inputs or budgets")


def prepare_carried_checkpoint(frozen_protocol):
    """Prepare zero-call protocol, then import every old outcome before normal resume."""
    frozen = json.loads(Path(frozen_protocol).read_bytes())
    binding = frozen["checkpoint_parent"]
    _, seeds, attempts = checkpoint_inventory(binding)
    directory = study_directory("DS21-005", "collapsed")
    if (directory / "checkpoint-migration.json").exists():
        validate_checkpoint_migration(directory, frozen, frozen_protocol)
        return dict(state="complete", carried_fit_calls=12, optimizer_calls=0)
    if not (directory / "protocol.json").exists():
        with patch("ds21_joint_proposals.fit_group_calibration",
                   side_effect=AssertionError("Checkpoint preparation must never optimize")):
            result = run("DS21-005", "collapsed", frozen_protocol, maximum_seconds=0.001,
                         _prepare_checkpoint=True)
        if result["state"] != "checkpointed":
            raise ValueError("Zero-call checkpoint preparation did not stop before fitting")
    else:
        # Partial imports may already contain all fits. Never enter the common
        # runner here: finish the import without scoring, sealing, or fitting.
        import ds21_shared_proposals as shared

        case = shared.load_case_with_proposals("DS21-005")
        validate_frozen_protocol(frozen_protocol, "DS21-005", "collapsed", case)
        protocol = json.loads((directory / "protocol.json").read_bytes())
        if protocol["scientific_control"]["frozen_protocol_sha256"] != digest(
            Path(frozen_protocol)
        ):
            raise ValueError("Partial checkpoint belongs to another frozen protocol")
        validate_archives(directory, protocol, require_mapping=True)
    protocol_sha = digest(directory / "protocol.json")
    raw = {"protocol.json": binding["protocol_sha256"]}
    raw.update({f"seeds/{n}": s for n, s in binding["seed_sha256"].items()})
    raw.update({f"attempts/{n}": s for n, s in binding["attempt_sha256"].items()})
    active_hashes = {}
    for relative, sha in raw.items():
        original_path = Path(binding["directory"]) / relative
        copied = directory / "checkpoint-parent" / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        if not copied.exists():
            copied.write_bytes(original_path.read_bytes())
        if digest(copied) != sha:
            raise ValueError("Preserve mismatched partial checkpoint copy")
        if relative == "protocol.json":
            continue
        old = (seeds if relative.startswith("seeds/") else attempts)[Path(relative).name]
        row = deepcopy(old)
        row["protocol_sha256"] = protocol_sha
        # No-vector failures are still outcomes: import them without evaluation,
        # diagnostics, retries, clipping, or any modification of the fit dict.
        immutable(directory / relative, row)
        active_hashes[relative] = digest(directory / relative)
    immutable(directory / "checkpoint-migration.json", dict(
        state="complete", parent=binding, new_protocol_sha256=protocol_sha,
        new_frozen_protocol_sha256=digest(Path(frozen_protocol)), active_sha256=active_hashes,
        optimizer_calls=0, carried_fit_calls=12,
    ))
    validate_checkpoint_migration(directory, frozen, frozen_protocol)
    return dict(state="complete", carried_fit_calls=12, optimizer_calls=0)


def candidate_objective(case, source, observations, *, variant):
    if variant not in VARIANTS:
        raise ValueError("Unknown native-candidate variant")
    if variant == "all-candidates":
        evidence, families, metadata = all_native_candidate_inputs(source, observations)
    else:
        evidence, families, labels = native_branch_inputs(source, observations)
        metadata = dict(native_branch_labels=labels,
                        collapsed_winner_ids=tuple(tuple(x for x in row if x)
                                                   for row in evidence.candidate_ids))
    base = NativeCandidateSingletonObjective(
        observations, case["bank"], case["prior"], HARD60_SCORE,
        sample_rate_hz=case["source"].sample_rate_hz, branch_evidence=evidence,
        family_keys=families, maximum_gap_s=case["source"].probe_ms / 1000 * 1.25,
    )
    metadata = {
        **metadata, "variant": variant, "native_candidates": int(evidence.available.sum()),
        "temporal_edges": 0, "sampling_period_hz": base.sample_rate_hz,
        "waveform": "neutral; no measured evidence",
    }
    model = GroupCalibrationObjective(base, observations.channel >= 5)
    model.candidate_inventory_metadata = metadata
    return model, metadata


def candidate_diagnostics(model, terms, metadata):
    retained = np.array([
        [identifier in set(winners) for identifier in row]
        for row, winners in zip(model.base.branches.candidate_ids,
                                metadata["collapsed_winner_ids"], strict=True)
    ])
    mass = float(terms.candidate_responsibilities.sum())
    discarded = float(terms.candidate_responsibilities[~retained].sum())
    return dict(
        posterior_native_residual_rms_hz=terms.posterior_native_residual_rms_hz,
        posterior_signal_mass=mass, discarded_alternative_posterior_mass=discarded,
        discarded_alternative_signal_fraction=discarded / mass if mass else None,
        legacy_posterior_rms_definition="RMS of branch-averaged residuals; may hide disagreement",
    )


def candidate_held_prediction(case, source, observations, training_model, fit, *, variant):
    model, metadata = candidate_objective(case, source, observations, variant=variant)
    correction = freeze_group_calibration(training_model, fit)
    vector = np.asarray(fit["vector"])
    shifts = vector[7] + training_model.basis @ vector[8:]
    prediction, visible = [], []
    for obs in model.base.branch_observations:
        values = predict_orbits(case["bank"], obs, case["prior"], vector[:2], shifts,
                               derivatives=False)
        prediction.append(values[0] + correction.predict(
            obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5,
        )[:, None])
        visible.append(values[1])
    terms, _ = model.base.likelihood(np.stack(prediction, axis=2), np.stack(visible, axis=2))
    return dict(
        windows=len(observations.window_ids), nll=terms.nll,
        nll_per_window=terms.nll / len(observations.window_ids),
        signal_windows=float(terms.responsibilities.sum()),
        clutter_windows=float(terms.clutter_probability.sum()),
        window_ids=observations.window_ids, metadata=metadata,
        candidate_diagnostics=candidate_diagnostics(model, terms, metadata),
        held_fitting="none; training correction, position and timing frozen",
    )


def held_comparison(case, source, observations, model, fit, *, variant):
    own = candidate_held_prediction(case, source, observations, model, fit, variant=variant)
    common = own if variant == "all-candidates" else candidate_held_prediction(
        case, source, observations, model, fit, variant="all-candidates",
    )
    return dict(own=own, common_all_candidates=common,
                comparison="Common all-candidate score primary; no held fitting/selection")


def collapsed_oracle_replay(case, parent):
    """Evaluate six original seeds and twelve saved endpoints; never optimize/select."""
    observations, source = case["prepared"]["all"].observations, case["split"].training
    old, _ = native_objective(case, source, observations)
    new, _ = candidate_objective(case, source, observations, variant="collapsed")
    terminal = json.loads((Path(parent) / "terminal.json").read_bytes())
    rows = [(f"seed-{i}", json.loads((Path(parent) / "seeds" / f"all-{i}.json")
                                   .read_bytes())["seed"]) for i in range(6)]
    for arm in FROZEN_FIELDS["arms"]:
        attempts = terminal["results"]["all"]["attempts"][arm]
        if len(attempts) != 6:
            raise ValueError("Oracle requires all original endpoints, including failed paths")
        rows += [(f"{arm}-{i}", row["fit"]) for i, row in enumerate(attempts)]
    results = []
    for name, state in rows:
        vector, nuisance = np.asarray(state["vector"]), np.asarray(state["nuisance"])
        previous = old.evaluate_joint(vector, nuisance)
        current = new.evaluate_joint(vector, nuisance)
        arrays = [(previous[i], current[i]) for i in range(3)] + [
            (previous[3].nll, current[3].nll),
            (previous[3].responsibilities, current[3].responsibilities),
            (previous[3].clutter_probability, current[3].clutter_probability),
            (previous[3].residual_hz, current[3].residual_hz),
        ]
        passed = all(np.allclose(a, b, atol=FROZEN_FIELDS["oracle_atol"],
                                 rtol=FROZEN_FIELDS["oracle_rtol"]) for a, b in arrays)
        results.append(dict(state=name, passed=passed,
                            maximum_absolute_difference=max(float(np.max(abs(
                                np.asarray(a) - np.asarray(b)), initial=0)) for a, b in arrays)))
    return results


def run(label, variant, frozen_protocol, *, maximum_seconds=500, _prepare_checkpoint=False):
    import ds21_shared_proposals as shared

    started = time.monotonic()
    if (label not in FROZEN_FIELDS["labels"] or variant not in VARIANTS
            or not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 500):
        raise ValueError("Case/variant/slice outside bounded candidate control")
    case = shared.load_case_with_proposals(label)
    frozen, sources, parent = validate_frozen_protocol(frozen_protocol, label, variant, case)
    policy = f"joint-native-candidate-{variant}-v2"
    directory = study_directory(label, variant)
    carried = dict(label=label, variant=variant) == FROZEN_FIELDS["carried_condition"]
    if _prepare_checkpoint:
        if not carried or maximum_seconds >= FROZEN_FIELDS["fit_seconds"]:
            raise ValueError("Zero-call preparation allowed only for the carried condition")
    elif carried:
        validate_checkpoint_migration(directory, frozen, frozen_protocol)
    terminal_path, protocol_path = directory / "terminal.json", directory / "protocol.json"

    def stored_seed(view, index):
        if view != "all" or index not in range(6):
            raise ValueError("Stored seed outside original six all-view starts")
        row = json.loads((parent / "seeds" / f"all-{index}.json").read_bytes())
        return row["seed"], row["receiver_branch_lifts"]

    def validate_seed(view, index, seed, lifts):
        original, expected_lifts = stored_seed(view, index)
        serialized = json.loads(json.dumps(seed, default=lambda value: value.tolist()))
        if serialized != original or lifts != expected_lifts:
            raise ValueError("Candidate-control physical seed/lift differs from parent")

    if terminal_path.exists():
        terminal, protocol = (json.loads(p.read_bytes()) for p in (terminal_path, protocol_path))
        control = protocol["scientific_control"]
        if (terminal["protocol_sha256"] != digest(protocol_path)
                or control["frozen_protocol_sha256"] != digest(Path(frozen_protocol))
                or control["variant"] != variant or protocol["effective_views"] != ["all"]
                or protocol["fit_diagnostics_key"] != "candidate_diagnostics"
                or set(terminal["results"]) != {"all"}
                or any(protocol["sources"].get(str(p)) != digest(p) for p in sources.values())
                or any(digest(Path(p)) != sha for p, sha in protocol["sources"].items())):
            raise ValueError("Sealed terminal belongs to a different candidate control")
        validate_archives(directory, protocol, require_mapping=True)
        validate_terminal_structure(terminal, protocol, case, frozen, label, variant)
        for index in range(6):
            row = json.loads((directory / "seeds" / f"all-{index}.json").read_bytes())
            if row["protocol_sha256"] != digest(protocol_path):
                raise ValueError("Sealed candidate-control seed protocol differs")
            validate_seed("all", index, row["seed"], row["receiver_branch_lifts"])
        return terminal

    def diagnostics(model, fit):
        terms = model.evaluate_joint(np.asarray(fit["vector"]), np.asarray(fit["nuisance"]))[3]
        return candidate_diagnostics(model, terms, model.candidate_inventory_metadata)

    dependencies = loaded_scientific_dependencies()
    paths = tuple(dict.fromkeys((*sources.values(), *(Path(x["path"])
                                                     for x in dependencies.values()),
                                *(Path(p) for p in frozen["loaded_source_sha256"]))))
    return run_proposals(
        label, maximum_seconds=maximum_seconds, policy=policy,
        objective_port=lambda c, s, o: candidate_objective(c, s, o, variant=variant),
        held_port=lambda c, s, o, m, f: held_comparison(c, s, o, m, f, variant=variant),
        extra_sources=paths, views=("all",), validate_seed=validate_seed,
        stored_seed_port=stored_seed, fit_diagnostics=diagnostics,
        fit_diagnostics_key="candidate_diagnostics", case_input=case, started_at=started,
        scientific_protocol=dict(
            frozen_protocol_path=str(Path(frozen_protocol).resolve()),
            frozen_protocol_sha256=digest(Path(frozen_protocol)), variant=variant, views=["all"],
            model_changes="Candidate inventory only; fixed per-cell mass and singleton core",
            equivalence="Collapsed numerically equivalent to source default, not bitwise identical",
            bank_limitation="Cannot recover a satellite absent from the original fixed bank",
            projection_diagnostics="Inherited original inventory; not a new projection",
            loaded_dependencies=dependencies, parent_binding=frozen["cases"][label],
            loaded_source_sha256=frozen["loaded_source_sha256"],
            checkpoint_parent=frozen["checkpoint_parent"] if carried else None,
            oracle_receipt_sha256=frozen["oracle_receipt_sha256"],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=FROZEN_FIELDS["labels"], required=True)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--frozen-protocol", type=Path, required=True)
    parser.add_argument("--maximum-seconds", type=float, default=500)
    args = parser.parse_args()
    result = run(args.label, args.variant, args.frozen_protocol,
                 maximum_seconds=args.maximum_seconds)
    print(json.dumps(dict(state=result.get("state", "sealed"), elapsed_s=result["elapsed_s"])))
