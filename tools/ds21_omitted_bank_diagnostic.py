"""Frozen training-only omitted-bank audit; named-module entrypoint, no fits.

Freeze is metadata/code-only. Run requires that exact immutable protocol and
one externally bounded process (495-second TERM, five-second KILL grace).
No held projector, reference evaluator, discovery or optimizer is invoked.
"""

import argparse
import hashlib
import json
import runpy
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from ds20_channel_corpus import ADAPTER, bounded, digest
from ds21_common import immutable, load_source
from joint_association_candidates_native import all_native_candidate_inputs

from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.joint_association_candidates import NativeCandidateSingletonObjective
from leo.analysis.research.omitted_bank_native import (
    compressed_native_gram,
    omitted_native_density,
    singleton_native_terms,
    window_parameter_scores,
)
from leo.analysis.research.omitted_bank_score import (
    omitted_component_scores,
    project_omitted_scores,
)
from leo.application.channel_group_holdout import partition_channel_probes
from leo.application.hard60_runner import HARD60_SCORE
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior

LABELS = ("DS21-005", "DS21-023")
ARMS = ("fitted-c", "zero-c")
POLICY = dict(
    name="conditional-omitted-bank-training-v1",
    labels=list(LABELS),
    arms=list(ARMS),
    selector="Minimum stationary training objective; start index tie-break; no fallback",
    optimizer_calls=0,
    held_preparation=False,
    held_scoring=False,
    reference_usage="none",
    omitted_timing="Winner common shift plus zero relative shift; no scan",
    omitted_chunk=32,
    latent_block_rows=2048,
    calculation_seconds=450,
    internal_seconds=480,
    external_term_seconds=495,
    external_kill_seconds=500,
    threads=1,
    geometry="Nuisance-only fixed-responsibility local design; no confidence claim",
)


def read_bound(binding):
    path = Path(binding["path"])
    if digest(path) != binding["sha256"]:
        raise ValueError(f"Bound input differs: {path}")
    return json.loads(path.read_bytes())


def fit_digest(value):
    """Exact metadata audit encoding, including its default ASCII escaping."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def scientific_sources():
    # Code-only preload includes the native binary and adapter's import closure.
    # No adapter loader function or numerical predictor is called by freeze.
    from leo.analysis import _regional_orbits

    runpy.run_path(str(ADAPTER))
    result = {str(Path(__file__).resolve()): digest(Path(__file__))}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename:
            path = Path(filename).resolve()
            if path.is_file() and ("/src/leo/" in str(path) or "/tools/" in str(path)):
                result[str(path)] = digest(path)
    result[str(ADAPTER)] = digest(ADAPTER)
    result[str(Path(_regional_orbits.__file__).resolve())] = digest(Path(_regional_orbits.__file__))
    return result


def select_training_winners(case):
    """Only the twelve training receipts enter selection; terminal bytes never parsed."""
    parent_sha = case["parent"]["protocol"]["sha256"]
    rows = {arm: [] for arm in ARMS}
    if len(case["attempts"]) != 12 or len(case["seeds"]) != 6:
        raise ValueError("Complete six-start/two-arm training inventory required")
    for filename, binding in case["attempts"].items():
        receipt = read_bound(binding)
        arm, start = binding["arm"], binding["start"]
        if (
            arm not in ARMS
            or start not in range(6)
            or filename != f"all-{start}-{arm}.json"
            or receipt["protocol_sha256"] != parent_sha
            or fit_digest(receipt["fit"]) != binding["fit_content_sha256"]
        ):
            raise ValueError("Training attempt identity differs")
        fit = receipt["fit"]
        if (
            fit.get("converged")
            and fit.get("stationarity", float("inf")) <= 0.001
            and np.isfinite(fit.get("objective", float("inf")))
            and "vector" in fit
            and "nuisance" in fit
        ):
            rows[arm].append(dict(start=start, fit=fit, attempt_filename=filename))
    winners = {}
    for arm, eligible in rows.items():
        winner = (
            min(eligible, key=lambda r: (r["fit"]["objective"], r["start"])) if eligible else None
        )
        declared = case["winners"][arm]
        if winner is None:
            if declared["state"] == "selected":
                raise ValueError("Declared winner lacks stationary training support")
            winners[arm] = None
        else:
            if (
                declared["state"] != "selected"
                or declared["start"] != winner["start"]
                or declared["attempt_filename"] != winner["attempt_filename"]
                or declared["fit"] != winner["fit"]
            ):
                raise ValueError("Declared winner differs from training-only selector")
            winners[arm] = winner
    return winners


def validate_inventory(binding):
    manifest = read_bound(binding)
    if manifest["schema"] != "conditional-omitted-bank-metadata-v1" or manifest["labels"] != list(
        LABELS
    ):
        raise ValueError("Fixed development-only diagnostic inventory required")
    membership = read_bound(manifest["membership"])
    if digest(Path(manifest["audit_recipe"]["path"])) != manifest["audit_recipe"]["sha256"]:
        raise ValueError("Diagnostic metadata audit recipe changed")
    # Byte seals are checked before source parsing or bank-array interpretation.
    for label in LABELS:
        case = manifest["cases"][label]
        if case["state"] != "ready":
            continue
        for section, names in (
            ("parent", ("protocol", "terminal", "frozen_protocol")),
            ("discovery", ("protocol", "bank_npz", "bank_json")),
            ("proposals", ("protocol", "terminal")),
        ):
            for name in names:
                receipt = case[section][name]
                if digest(Path(receipt["path"])) != receipt["sha256"]:
                    raise ValueError("Diagnostic parent/bank/proposal seal changed")
        if digest(Path(case["source_input"]["path"])) != case["source_input"]["sha256"]:
            raise ValueError("Original tracking input changed")
        member = next(m for m in membership["members"] if m["label"] == label)
        if (
            member["role"] != "development"
            or not member["eight_channel"]
            or member["input"] != case["source_input"]
            or member["raw_identity"] != case["member"]["raw_identity"]
        ):
            raise ValueError("Diagnostic membership/input authority differs")
        parent = read_bound(case["parent"]["protocol"])
        discovery = read_bound(case["discovery"]["protocol"])
        proposals = read_bound(case["proposals"]["protocol"])
        bank_receipt = read_bound(case["discovery"]["bank_json"])
        if (
            parent["shared_discovery_sha256"] != case["discovery"]["protocol"]["sha256"]
            or parent["prepared"]["all"] != case["parent"]["prepared_all_sha256"]
            or parent["catalogue_numbers"] != case["proposals"]["candidate_numbers"]
            or parent["proposal_binding"]["protocol_sha256"]
            != case["proposals"]["protocol"]["sha256"]
            or discovery["membership_sha256"] != manifest["membership"]["sha256"]
            or discovery["input_sha256"] != case["source_input"]["sha256"]
            or bank_receipt["sha256"] != case["discovery"]["bank_npz"]["sha256"]
            or proposals["candidate_full_indices"] != case["proposals"]["candidate_full_indices"]
            or proposals["candidate_numbers"] != case["proposals"]["candidate_numbers"]
        ):
            raise ValueError("Training input/bank/proposal transitivity differs")
        for seed in case["seeds"].values():
            read_bound(seed)
        select_training_winners(case)
    return manifest, membership


def draft_protocol(manifest_path, output):
    """No data preparation/orbit computation: exact metadata and code-only binding."""
    binding = dict(path=str(Path(manifest_path).resolve()), sha256=digest(Path(manifest_path)))
    validate_inventory(binding)
    return dict(
        schema="omitted-bank-diagnostic-protocol-v1",
        policy=POLICY,
        metadata=binding,
        output=str(Path(output).resolve()),
        sources=scientific_sources(),
    )


def validate_protocol(path):
    frozen = json.loads(Path(path).read_bytes())
    if (
        frozen["schema"] != "omitted-bank-diagnostic-protocol-v1"
        or frozen["policy"] != POLICY
        or frozen["sources"] != scientific_sources()
    ):
        raise ValueError("Frozen diagnostic policy/source changed")
    manifest, membership = validate_inventory(frozen["metadata"])
    return frozen, manifest, membership


def training_case(case, membership):
    """Existing narrow ports only; no held projection or bootstrap fitting."""
    member = next(m for m in membership["members"] if m["label"] == case["member"]["label"])
    source = load_source(member, membership)
    split = partition_channel_probes(source)
    prepared = prepare_position_windows(split.training)
    if prepared.evidence_sha256 != case["parent"]["prepared_all_sha256"]:
        raise ValueError("Training-only preparation differs from sealed input")
    with np.load(case["discovery"]["bank_npz"]["path"], allow_pickle=False) as arrays:
        full = PositionOrbitBank(
            *(arrays[k] for k in ("numbers", "nodes_s", "position_km", "velocity_km_s"))
        )
    indices = case["proposals"]["candidate_full_indices"]
    bank = full.select(indices)
    if bank.numbers.tolist() != case["proposals"]["candidate_numbers"]:
        raise ValueError("Selected bank identity/order differs from saved timing basis")
    omitted = sorted(set(range(len(full.numbers))) - set(indices), key=lambda i: full.numbers[i])
    if (
        len(full.numbers) != case["discovery"]["full_count"]
        or canonical_digest(full.numbers.tolist()) != case["discovery"]["full_number_order_sha256"]
        or len(omitted) != case["bank_relation"]["omitted_count"]
    ):
        raise ValueError("Complete causal-bank inventory differs")
    evidence, families, metadata = all_native_candidate_inputs(
        split.training, prepared.observations
    )
    base = NativeCandidateSingletonObjective(
        prepared.observations,
        bank,
        RegionalPrior(**membership["prior"]),
        HARD60_SCORE,
        sample_rate_hz=source.sample_rate_hz,
        branch_evidence=evidence,
        family_keys=families,
        maximum_gap_s=source.probe_ms / 1000 * 1.25,
    )
    model = GroupCalibrationObjective(base, prepared.observations.channel >= 5)
    if model.clock_count or model.group_count != model.offset_count:
        raise ValueError("Frozen lean affine/group diagnostic basis required")
    return dict(
        model=model,
        full_bank=full,
        omitted=omitted,
        prepared=prepared,
        source=split.training,
        metadata=metadata,
        block_seconds=split.block_seconds,
    )


def active_constraints(model, vector, nuisance, seed):
    """Report coupled limits explicitly; projection remains unconstrained."""
    names, calibration = [], []
    for index, label, limit in ((3, "rx0_drift", 60), (5, "rx1_drift", 60), (6, "c", 5000)):
        if abs(vector[index]) >= limit - 1e-7:
            names.append(label)
            calibration.append(index - 2)
    shifts = vector[7] + model.basis @ vector[8:]
    for i in np.flatnonzero(abs(shifts) >= 20 - 1e-6):
        names.append(f"total_timing:{int(model.bank.numbers[i])}")
    if abs(vector[7]) >= 10 - 1e-7:
        names.append("common_timing")
    for i in np.flatnonzero(abs(nuisance) >= model.group_limits - 1e-7):
        names.append(f"group:{model.frame.receivers[i]}")
        calibration.append(5 + int(i))
    if np.linalg.norm(vector[:2]) >= model.prior.radius_km - 1e-6:
        names.append("prior_disk")
    if np.linalg.norm(vector[:2] - np.asarray(seed["seed"]["vector"][:2])) >= 25 - 1e-6:
        names.append("local_25km_disk")
    return names, calibration


def grouped_scores(projection, numbers, observations, block_seconds):
    groups = {}
    for name, labels in (
        ("receiver", observations.receiver),
        ("training_block", np.floor(observations.times_s / block_seconds).astype(int)),
    ):
        groups[name] = [
            dict(
                group=int(value),
                windows=int(np.sum(labels == value)),
                raw_sum=projection.raw_scores[labels == value].sum(axis=0).tolist(),
                projected_sum=projection.projected_scores[labels == value].sum(axis=0).tolist(),
            )
            for value in np.unique(labels)
        ]
    return dict(
        numbers=numbers,
        raw_sum=projection.raw_sum.tolist(),
        projected_sum=projection.projected_sum.tolist(),
        projected_norm_fraction=projection.projected_norm_fraction,
        groups=groups,
        all_parameter_space=asdict(projection.all_parameter_space),
        warnings=projection.warnings,
    )


def diagnose_state(case, winner, arm, *, guard, progress, progress_port=lambda numbers: None):
    model, full = case["model"], case["full_bank"]
    fit = winner["fit"]
    vector, nuisance = np.asarray(fit["vector"]), np.asarray(fit["nuisance"])
    if (
        vector.shape != (model.size,)
        or nuisance.shape != model.initial_nuisance.shape
        or not np.isfinite(vector).all()
        or not np.isfinite(nuisance).all()
        or (arm == "zero-c" and vector[6] != 0)
    ):
        raise ValueError("Saved winner differs from fixed free-parameter basis")
    if fit["training_high_fractions"] != list(model.frame.high_fractions) or fit[
        "group_receivers"
    ] != list(model.frame.receivers):
        raise ValueError("Training group-centering frame changed")
    base, obs = model.base, model.base.native_observations
    rows, slots = base.native_rows, base.native_slots
    shifts = vector[7] + model.basis @ vector[8:]
    guard()
    prediction, visible, spatial, timing = predict_orbits(
        model.bank, obs, model.prior, vector[:2], shifts
    )
    correction = (
        base.native_design @ vector[2:7] + base.baseline[rows] + model.group_design[rows] @ nuisance
    )
    prediction += correction[:, None]
    terms = singleton_native_terms(
        obs.measured_hz,
        prediction,
        visible,
        rows,
        slots,
        base.metadata_log_emission_prior,
        base.initial,
        sigma_hz=model.score.sigma_hz,
        sample_rate_hz=base.sample_rate_hz,
    )
    if not np.isclose(terms.nll, fit["likelihood_nll"], atol=1e-7, rtol=0):
        raise ValueError("Frozen winner native likelihood replay changed")
    calibration = np.column_stack([base.native_design, model.group_design[rows]])
    labels = ["rx0_offset", "rx0_drift", "rx1_offset", "rx1_drift", "c"]
    labels += [f"group:{rx}" for rx in model.frame.receivers]
    active, active_cal = active_constraints(model, vector, nuisance, winner["seed"])
    keep = [i for i in range(len(labels)) if arm != "zero-c" or i != 4]
    calibration, labels = calibration[:, keep], [labels[i] for i in keep]
    active_nuisance = tuple(keep.index(i) for i in active_cal if i in keep)
    labels += ["common_timing"] + [f"relative_basis:{i}" for i in range(model.basis.shape[1])]
    if "common_timing" in active:
        active_nuisance += (calibration.shape[1],)
    geo_score, nuisance_score = window_parameter_scores(
        rows,
        terms.log_prediction_weight,
        spatial,
        timing,
        calibration,
        model.basis,
        windows=len(model.observations.window_ids),
    )
    guard()
    gram = compressed_native_gram(
        terms.posterior,
        spatial,
        timing,
        calibration,
        model.basis,
        sigma_hz=model.score.sigma_hz,
        block_rows=POLICY["latent_block_rows"],
        active_nuisance_bounds=active_nuisance,
        guard=guard,
    )
    omitted = case["omitted"]
    scores = np.empty((len(model.observations.window_ids), len(omitted)))
    prior = base.metadata_candidate_prior[rows, slots]
    for start in range(0, len(omitted), POLICY["omitted_chunk"]):
        guard()
        ids = omitted[start : start + POLICY["omitted_chunk"]]
        bank = full.select(ids)
        pred, available, _, _ = predict_orbits(
            bank,
            obs,
            model.prior,
            vector[:2],
            np.full(len(ids), vector[7]),
            derivatives=False,
        )
        density = omitted_native_density(
            obs.measured_hz,
            pred + correction[:, None],
            available,
            rows,
            prior,
            windows=len(scores),
            sigma_hz=model.score.sigma_hz,
            sample_rate_hz=base.sample_rate_hz,
        )
        scores[:, start : start + len(ids)] = omitted_component_scores(
            terms.current_signal_density,
            density,
            signal_mass=terms.signal_mass,
            clutter_density=terms.clutter_density,
        )
        progress.extend(bank.numbers.tolist())
        progress_port(progress)
    guard()
    projection = project_omitted_scores(
        scores, geo_score, nuisance_score, active_nuisance_bounds=active_nuisance
    )
    guard()
    return dict(
        state="complete",
        coverage_complete=True,
        optimizer_calls=0,
        winner_start=winner["start"],
        likelihood_nll=terms.nll,
        basis=["east", "north", *labels],
        active_constraints=active,
        latent_rows=int(terms.posterior.size),
        native_candidates=len(obs.window_ids),
        signal_mass=float(terms.posterior.sum()),
        geographic_gram=asdict(gram),
        omitted=grouped_scores(projection, progress, model.observations, case["block_seconds"]),
        constraint_warning=(
            "Unconstrained tangent projection; coupled limits are not a feasible cone."
        ),
    )


def run(protocol_path):
    started = time.monotonic()
    frozen, manifest, membership = validate_protocol(protocol_path)
    directory = Path(frozen["output"])
    terminal = directory / "terminal.json"
    protocol_sha = digest(Path(protocol_path))
    if terminal.exists():
        saved = json.loads(terminal.read_bytes())
        if saved["protocol_sha256"] != protocol_sha:
            raise ValueError("Existing diagnostic terminal belongs to another freeze")
        return saved
    if (directory / "started.json").exists():
        raise ValueError(
            "Diagnostic slice already started without terminal; no automatic second slice"
        )
    immutable(directory / "protocol.json", frozen)
    immutable(
        directory / "started.json",
        dict(
            protocol_sha256=protocol_sha,
            optimizer_calls=0,
            policy="One slice; interrupted runs cannot restart",
        ),
    )
    results, progress, current = {}, [], None

    def save_state(label, arm, result):
        immutable(
            directory / "states" / f"{label}-{arm}.json",
            dict(protocol_sha256=protocol_sha, label=label, arm=arm, result=result),
        )

    def guard():
        if time.monotonic() - started >= POLICY["calculation_seconds"]:
            raise TimeoutError("Fixed 450-second calculation budget exhausted")

    try:
        with bounded(max(0.001, POLICY["internal_seconds"] - (time.monotonic() - started))):
            for label in LABELS:
                metadata_case = manifest["cases"][label]
                results[label] = {}
                current, progress = (label, None), []
                if metadata_case["state"] != "ready":
                    results[label] = {
                        arm: dict(state="unavailable", coverage_complete=False) for arm in ARMS
                    }
                    continue
                try:
                    guard()
                    case = training_case(metadata_case, membership)
                except ValueError as error:
                    for arm in ARMS:
                        results[label][arm] = dict(
                            state="preparation-failed",
                            reason=str(error),
                            coverage_complete=False,
                            optimizer_calls=0,
                        )
                        save_state(label, arm, results[label][arm])
                    continue
                winners = select_training_winners(metadata_case)
                for arm in ARMS:
                    progress, current = [], (label, arm)
                    winner = winners[arm]
                    if winner is None:
                        results[label][arm] = dict(state="unavailable", coverage_complete=False)
                        continue
                    winner["seed"] = read_bound(
                        metadata_case["seeds"][f"all-{winner['start']}.json"]
                    )
                    try:

                        def save_progress(numbers, label=label, arm=arm):
                            immutable(
                                directory / "progress" / f"{label}-{arm}-{len(numbers)}.json",
                                dict(
                                    protocol_sha256=protocol_sha,
                                    label=label,
                                    arm=arm,
                                    completed_numbers=numbers,
                                    coverage_complete=False,
                                    partial_score_ranking=False,
                                    optimizer_calls=0,
                                ),
                            )

                        results[label][arm] = diagnose_state(
                            case,
                            winner,
                            arm,
                            guard=guard,
                            progress=progress,
                            progress_port=save_progress,
                        )
                    except ValueError as error:
                        results[label][arm] = dict(
                            state="failed",
                            reason=str(error),
                            coverage_complete=False,
                            completed_numbers=progress,
                            optimizer_calls=0,
                        )
                    save_state(label, arm, results[label][arm])
    except TimeoutError as error:
        if current:
            label, arm = current
            for failed_arm in ARMS if arm is None else (arm,):
                results.setdefault(label, {})[failed_arm] = dict(
                    state="preparation-timeout" if arm is None else "timeout",
                    reason=str(error),
                    coverage_complete=False,
                    completed_numbers=progress,
                    optimizer_calls=0,
                    partial_score_ranking=False,
                )
                save_state(label, failed_arm, results[label][failed_arm])
    for label in LABELS:
        for arm in ARMS:
            results.setdefault(label, {}).setdefault(
                arm, dict(state="not-attempted", coverage_complete=False)
            )
    # Reserve the final 30 seconds for compact immutable receipts/source gates.
    validate_protocol(protocol_path)
    receipt = dict(
        schema="omitted-bank-diagnostic-terminal-v1",
        protocol_sha256=protocol_sha,
        state="complete"
        if all(r["coverage_complete"] for c in results.values() for r in c.values())
        else "incomplete",
        coverage_complete=all(r["coverage_complete"] for c in results.values() for r in c.values()),
        results=results,
        elapsed_s=time.monotonic() - started,
        optimizer_calls=0,
        held_preparation=False,
        held_scoring=False,
        reference_usage="none",
    )
    immutable(terminal, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "freeze":
        if args.metadata is None or args.output is None:
            parser.error("freeze requires --metadata and --output")
        immutable(args.protocol, draft_protocol(args.metadata, args.output))
        result = dict(state="frozen", protocol_sha256=digest(args.protocol), optimizer_calls=0)
    else:
        result = run(args.protocol)
        result = {
            key: result[key]
            for key in ("state", "coverage_complete", "elapsed_s", "optimizer_calls")
        }
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
