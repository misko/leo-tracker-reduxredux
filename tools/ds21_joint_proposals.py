"""Unchanged neutral Model C on the frozen common six-start proposal pool."""

import argparse
import hashlib
import json
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
from ds20_channel_corpus import digest
from ds21_common import OUTPUT, immutable
from ds21_joint import held_prediction, objective, physical_receiver_branches

from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.joint_association_projection import (
    matched_joint_arm_seeds,
    project_native_joint_seed,
)
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.analysis.research.doppler_shape_shared_proposals import evaluate_physical_correction

POLICY = "joint-native-shared-sixstart-v2"


def reuse_decoder_checkpoint(parent, protocol, seed, branches, model, view, index, arm):
    """Reuse a partial v1 fit only after exact physical-seed and score replay.

    The canonical empty-array decoder correction changes no all-view physics.
    Its failed half-view invocation and immutable partial receipts remain intact.
    """
    attempt = parent / "attempts" / f"{view}-{index}-{arm}.json"
    if not attempt.exists():
        return None
    old_protocol_path = parent / "protocol.json"
    old = json.loads(old_protocol_path.read_bytes())
    excluded = {"policy", "sources", "decoder_checkpoint_migration"}
    if {k: v for k, v in old.items() if k not in excluded} != (
        {k: v for k, v in protocol.items() if k not in excluded}
    ):
        raise ValueError("Decoder checkpoint changed scientific protocol or common proposal inputs")
    allowed = {"ds21_joint_proposals.py", "doppler_shape_shared_proposals.py"}
    for filename, sha in old["sources"].items():
        saved = parent / "source-snapshot" / Path(filename).name
        if digest(saved) != sha:
            raise ValueError("Partial decoder checkpoint source snapshot differs")
        if Path(filename).name not in allowed and protocol["sources"].get(filename) != sha:
            raise ValueError("Scientific Model C implementation changed during decoder checkpoint")
    previous_seed = json.loads((parent / "seeds" / f"{view}-{index}.json").read_bytes())
    if previous_seed["seed"] != json.loads(json.dumps(seed, default=lambda v: v.tolist())):
        raise ValueError("Decoded physical seed differs from the partial checkpoint")
    if previous_seed["receiver_branch_lifts"] != branches:
        raise ValueError("Physical receiver integer lift changed during decoder checkpoint")
    receipt = json.loads(attempt.read_bytes())
    if receipt["protocol_sha256"] != digest(old_protocol_path):
        raise ValueError("Partial decoder fit receipt belongs to another protocol")
    fit = receipt["fit"]
    if "vector" not in fit:
        return None
    value, _, _, _ = model.evaluate_joint(np.asarray(fit["vector"]), np.asarray(fit["nuisance"]))
    if not np.isclose(value, fit["objective"], atol=1e-7, rtol=0):
        raise ValueError("Partial decoder fit objective changed under exact replay")
    return dict(
        fit=fit,
        reuse=dict(
            parent_protocol_sha256=digest(old_protocol_path),
            parent_fit_sha256=digest(attempt),
            parent_seed_sha256=digest(parent / "seeds" / f"{view}-{index}.json"),
            proof="Exact physical seed/lift equality; unchanged model; objective replay",
            objective_replay_delta=float(value - fit["objective"]),
        ),
    )


def physical_seed(model, proposal, evaluate_correction):
    """Consume only the shared pool's physical correction/timing ports."""
    values = evaluate_correction(proposal, model.base.native_observations)
    timing = proposal["orbit_timing"]
    numbers, shifts = timing["satellite_numbers"], timing["shifts_s"]
    if len(numbers) != len(set(numbers)) or len(numbers) != len(shifts):
        raise ValueError("One physical timing per unique proposal satellite required")
    if set(numbers) != set(model.bank.numbers.tolist()):
        raise ValueError("Physical proposal timings differ from the fixed candidate bank")
    by_number = dict(zip(numbers, shifts, strict=True))
    shifts = np.array([by_number[int(number)] for number in model.bank.numbers])
    return project_native_joint_seed(model, proposal["point_km"], shifts, values)


def proposal_start(
    model, proposal, branches, *, view, index, stored_seed_port=None, validate_seed=None,
):
    """Keep original physical starts when a controlled observation inventory changes.

    Stored states already include their sampling-integer lifts. Their inherited
    projection diagnostics describe the parent inventory, not a new projection.
    The caller's source-bound validator must verify the complete parent state.
    """
    if stored_seed_port is None:
        seed = physical_seed(model, proposal, evaluate_physical_correction)
        for branch in branches:
            seed["vector"][2 + 2 * branch["receiver"]] += branch["integer"] * ALIAS_HZ
    else:
        if validate_seed is None:
            raise ValueError("Stored physical starts require a parent-state validator")
        seed, saved_branches = stored_seed_port(view, index)
        if saved_branches != branches:
            raise ValueError("Stored physical starts changed their shared receiver lifts")
        seed = deepcopy(seed)
        seed["vector"] = np.array(seed["vector"], dtype=float, copy=True)
        seed["nuisance"] = np.array(seed["nuisance"], dtype=float, copy=True)
        if (
            seed["vector"].shape != (model.size,)
            or seed["nuisance"].shape != model.initial_nuisance.shape
            or not np.isfinite(seed["vector"]).all()
            or not np.isfinite(seed["nuisance"]).all()
        ):
            raise ValueError("Stored physical start differs from the target parameter layout")
    if validate_seed is not None:
        validate_seed(view, index, seed, branches)
    return seed


def attach_fit_diagnostics(model, fit, port, *, key="pair_diagnostics"):
    """Keep typed research diagnostics separate from optimizer result fields."""
    if key not in ("pair_diagnostics", "candidate_diagnostics"):
        raise ValueError("Unsupported research fit diagnostics key")
    if port is not None and "vector" in fit:
        fit[key] = port(model, fit)


def run(
    label, *, maximum_seconds=500, policy=POLICY, objective_port=objective,
    held_port=held_prediction, extra_sources=(), scientific_protocol=None,
    views=None, validate_seed=None, fit_diagnostics=None, case_input=None, started_at=None,
    stored_seed_port=None, fit_diagnostics_key="pair_diagnostics",
):
    import ds21_shared_proposals as shared

    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 500:
        raise ValueError("A resumable Model C slice must be bounded to at most500 seconds")
    if stored_seed_port is not None and (scientific_protocol is None or validate_seed is None):
        raise ValueError("Stored physical starts require a scientific protocol and validator")
    if fit_diagnostics_key not in ("pair_diagnostics", "candidate_diagnostics"):
        raise ValueError("Unsupported research fit diagnostics key")
    started = time.monotonic() if started_at is None else started_at
    case = shared.load_case_with_proposals(label) if case_input is None else case_input
    directory = OUTPUT / "local" / policy / label
    terminal = directory / "terminal.json"
    if terminal.exists():
        return json.loads(terminal.read_bytes())
    seeds = case["proposal_seeds"]
    identifiers = [row["id"] for row in seeds["all"]]
    if len(identifiers) != 6 or len(set(identifiers)) != 6:
        raise ValueError("Exactly six common physical proposal identifiers required")
    if any([row["id"] for row in rows] != identifiers for rows in seeds.values()):
        raise ValueError("Proposal order differs between channel views")
    binding = case["proposal_binding"]
    parent = (
        OUTPUT / "local/joint-native-shared-sixstart-v1" / label
        if policy == POLICY else directory / "no-decoder-parent"
    )
    source_paths = (
        Path(__file__),
        Path(shared.__file__),
        Path(__file__).with_name("ds21_joint.py"),
        Path(__file__).with_name("joint_association_native.py"),
        Path(__file__).parents[1] / "src/leo/analysis/joint_association_graph.py",
        Path(__file__).parents[1] / "src/leo/analysis/joint_association_score.py",
        Path(__file__).parents[1] / "src/leo/analysis/joint_association_sparse.py",
        Path(__file__).parents[1] / "src/leo/analysis/joint_association_projection.py",
        Path(__file__).parents[1] / "src/leo/analysis/research/doppler_shape_shared_proposals.py",
        Path(__file__).parents[1] / "src/leo/analysis/frozen_group_calibration.py",
    ) + tuple(extra_sources)
    protocol = dict(
        model="C",
        policy=policy,
        label=label,
        proposal_binding={key: str(value) for key, value in binding.items()},
        shared_discovery_sha256=case["protocol_sha256"],
        prepared={view: value.evidence_sha256 for view, value in case["prepared"].items()},
        catalogue_numbers=case["bank"].numbers.tolist(),
        proposal_ids=identifiers,
        fit_seconds=20,
        iterations=600,
        starts=6,
        c_arms=["fitted-c", "zero-c"],
        model_changes="None: native sampling-circle likelihood/graph/nuisance unchanged",
        waveform="Neutral; no new waveform measurements",
        calibration_transport="Window-weighted bounded function projection at native receive times",
        receiver_branch_start="All-training modal integer after projection; shared groups/arms",
        reference_usage="none",
        held_selection="none",
        decoder_checkpoint_migration=(
            dict(
                parent_protocol_sha256=digest(parent / "protocol.json"),
                reason="Canonical empty group-clock JSON decode; physical functions unchanged",
            )
            if (parent / "protocol.json").exists()
            else None
        ),
        sources={str(path): digest(path) for path in source_paths},
    )
    if scientific_protocol is not None:
        protocol["scientific_control"] = scientific_protocol
        protocol["model_changes"] = scientific_protocol["model_changes"]
        protocol["effective_views"] = list(views) if views is not None else list(case["prepared"])
    if stored_seed_port is not None:
        protocol["calibration_transport"] = "Exact saved parent vector/nuisance; no new projection"
        protocol["receiver_branch_start"] = (
            "Exact saved parent sampling-integer lifts; already applied"
        )
        protocol["projection_diagnostics"] = (
            "Inherited parent inventory; not recomputed on target rows"
        )
    if fit_diagnostics_key != "pair_diagnostics":
        protocol["fit_diagnostics_key"] = fit_diagnostics_key
    basenames = [Path(filename).name for filename in protocol["sources"]]
    snapshot_paths = {}
    for filename in protocol["sources"]:
        source = Path(filename)
        relative = (
            Path("by-path") / hashlib.sha256(str(source).encode()).hexdigest()[:16] / source.name
            if basenames.count(source.name) > 1 else Path(source.name)
        )
        snapshot_paths[filename] = relative
    if scientific_protocol is not None:
        protocol["source_snapshot_paths"] = {k: str(v) for k, v in snapshot_paths.items()}
    immutable(directory / "protocol.json", protocol)
    protocol_sha = digest(directory / "protocol.json")
    for filename, sha in protocol["sources"].items():
        source = Path(filename)
        saved = directory / "source-snapshot" / snapshot_paths[filename]
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.exists():
            saved.write_bytes(source.read_bytes())
        if digest(saved) != sha or digest(source) != sha:
            raise ValueError("Common-proposal Model C source snapshot differs")
    all_model, _ = objective_port(
        case, case["split"].training, case["prepared"]["all"].observations
    )
    branches = []
    for index, proposal in enumerate(seeds["all"]):
        if stored_seed_port is None:
            seed = physical_seed(all_model, proposal, evaluate_physical_correction)
            branches.append(physical_receiver_branches(all_model, seed))
        else:
            branches.append(deepcopy(stored_seed_port("all", index)[1]))
    immutable(directory / "receiver-branch-starts.json", branches)
    results = {}
    for view, prepared in case["prepared"].items():
        if views is not None and view not in views:
            continue
        model, metadata = objective_port(case, case["split"].training, prepared.observations)
        attempts = {arm: [] for arm in protocol["c_arms"]}
        for index, proposal in enumerate(seeds[view]):
            seed = proposal_start(
                model, proposal, branches[index], view=view, index=index,
                stored_seed_port=stored_seed_port, validate_seed=validate_seed,
            )
            immutable(
                directory / "seeds" / f"{view}-{index}.json",
                dict(
                    protocol_sha256=protocol_sha,
                    proposal_id=identifiers[index],
                    seed=seed,
                    receiver_branch_lifts=branches[index],
                ),
            )
            arm_seeds = matched_joint_arm_seeds(seed)
            for arm, initial in arm_seeds.items():
                path = directory / "attempts" / f"{view}-{index}-{arm}.json"
                if path.exists():
                    receipt = json.loads(path.read_bytes())
                    if receipt["protocol_sha256"] != protocol_sha:
                        raise ValueError("Common-proposal fit belongs to another protocol")
                    fit = receipt["fit"]
                else:
                    reused = (
                        reuse_decoder_checkpoint(
                            parent, protocol, seed, branches[index], model, view, index, arm
                        )
                        if (parent / "protocol.json").exists()
                        else None
                    )
                    if reused is not None:
                        fit = reused["fit"]
                        immutable(
                            path,
                            dict(
                                protocol_sha256=protocol_sha,
                                proposal_id=identifiers[index],
                                **reused,
                            ),
                        )
                        attempts[arm].append(
                            dict(
                                start=index,
                                proposal_id=identifiers[index],
                                fit=fit,
                                projection=seed["projection"],
                            )
                        )
                        print(
                            json.dumps(
                                dict(
                                    label=label,
                                    view=view,
                                    arm=arm,
                                    start=index,
                                    state="decoder-checkpoint-replayed",
                                )
                            ),
                            flush=True,
                        )
                        continue
                    if time.monotonic() - started + protocol["fit_seconds"] >= maximum_seconds:
                        return dict(
                            state="checkpointed",
                            next=str(path),
                            elapsed_s=time.monotonic() - started,
                        )
                    try:
                        fit = fit_group_calibration(
                            model,
                            initial["vector"],
                            initial["nuisance"],
                            arm=arm,
                            seconds=protocol["fit_seconds"],
                            iterations=protocol["iterations"],
                            local_center=initial["vector"][:2],
                            local_radius_km=25,
                        )
                    except (ValueError, TimeoutError) as error:
                        fit = dict(converged=False, reason=str(error))
                    attach_fit_diagnostics(
                        model, fit, fit_diagnostics, key=fit_diagnostics_key,
                    )
                    immutable(
                        path,
                        dict(protocol_sha256=protocol_sha, proposal_id=identifiers[index], fit=fit),
                    )
                attempts[arm].append(
                    dict(
                        start=index,
                        proposal_id=identifiers[index],
                        fit=fit,
                        projection=seed["projection"],
                    )
                )
                print(
                    json.dumps(
                        dict(
                            label=label,
                            view=view,
                            arm=arm,
                            start=index,
                            proposal_id=identifiers[index],
                            converged=fit["converged"],
                            elapsed_s=time.monotonic() - started,
                        )
                    ),
                    flush=True,
                )
        selected = {}
        for arm, rows in attempts.items():
            eligible = [row for row in rows if row["fit"]["converged"]]
            if not eligible:
                selected[arm] = dict(state="unavailable", reason="No stationary common-pool fit")
                continue
            winner = min(eligible, key=lambda row: (row["fit"]["objective"], row["start"]))
            selected[arm] = dict(
                **winner,
                held_prediction=held_port(
                    case, case["split"].held, case["held"][view], model, winner["fit"]
                ),
            )
        results[view] = dict(attempts=attempts, selected=selected, metadata=metadata)
    if any(digest(Path(filename)) != sha for filename, sha in protocol["sources"].items()):
        raise ValueError("Common-proposal Model C source changed before seal")
    result = dict(
        protocol_sha256=protocol_sha,
        results=results,
        reference_usage="none",
        proposal_binding=protocol["proposal_binding"],
        elapsed_s=time.monotonic() - started,
    )
    immutable(terminal, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--maximum-seconds", type=float, default=500)
    args = parser.parse_args()
    result = run(args.label, maximum_seconds=args.maximum_seconds)
    print(
        json.dumps(
            dict(
                label=args.label, state=result.get("state", "sealed"), elapsed_s=result["elapsed_s"]
            )
        )
    )
