"""One frozen training-only weight-profile selection slice; never fits a position."""

import argparse
import importlib
import json
import time
from pathlib import Path

import ds21_omitted_bank_diagnostic as original
import numpy as np
from ds20_channel_corpus import bounded, digest
from ds21_common import immutable

from leo.analysis.research.omitted_bank_selection import (
    project_with_weight_tangents,
    select_common_grouped_pool,
)

LABELS, ARMS = original.LABELS, original.ARMS
POLICY = dict(
    name="common-bank-weight-profile-selection-v1",
    labels=list(LABELS),
    arms=list(ARMS),
    weight_tangent="K * per-original-window satellite posterior @ zero_sum_basis(K); q fixed",
    eligibility=(
        "Both RX projected sums > 0 and total minus largest original20s block > 0 in BOTH arms"
    ),
    numerical_zero=(
        "Undefined norm ratio or projected/raw norm <= max(span rank tolerance, "
        "dim*eps); rank convention, not error bound"
    ),
    maximum_additions=4,
    rank="Descending minimum block-removed score across arms; catalogue tie",
    bank_order="Original unchanged prefix; additions in catalogue order",
    empty_pool="Unavailable; no fallback",
    omitted_timing="Winner common plus zero relative",
    omitted_chunk=32,
    calculation_seconds=450,
    internal_seconds=480,
    external_term_seconds=495,
    external_kill_seconds=500,
    optimizer_calls=0,
    held_preparation=False,
    held_scoring=False,
    reference_usage="none",
    threads=1,
)


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=digest(path))


def scientific_sources(fitting_module):
    fitting = importlib.import_module(fitting_module)  # Code-only; no case/fit port invoked.
    paths = fitting.scientific_sources()
    result = original.scientific_sources()
    result.update({str(Path(path).resolve()): digest(Path(path)) for path in paths.values()})
    result[str(Path(__file__).resolve())] = digest(Path(__file__))
    return result


def validate_parents(metadata_binding, completed):
    manifest, membership = original.validate_inventory(metadata_binding)
    protocol = original.read_bound(completed["protocol"])
    terminal = original.read_bound(completed["terminal"])
    if (
        protocol["metadata"] != metadata_binding
        or protocol["policy"] != original.POLICY
        or terminal["protocol_sha256"] != completed["protocol"]["sha256"]
        or not terminal["coverage_complete"]
        or terminal["optimizer_calls"] != 0
        or set(terminal["results"]) != set(LABELS)
    ):
        raise ValueError("Complete unchanged diagnostic/metadata parents required")
    for path, sha in protocol["sources"].items():
        if digest(Path(path)) != sha:
            raise ValueError("Completed diagnostic source bytes changed")
    for label in LABELS:
        for arm in ARMS:
            state = terminal["results"][label][arm]
            if (
                not state["coverage_complete"]
                or state["state"] != "complete"
                or state["winner_start"] != manifest["cases"][label]["winners"][arm]["start"]
            ):
                raise ValueError("Complete original training-winner coverage required")
    return manifest, membership, terminal


def draft_protocol(metadata, diagnostic_protocol, diagnostic_terminal, output, fitting_module):
    meta = binding(metadata)
    completed = dict(protocol=binding(diagnostic_protocol), terminal=binding(diagnostic_terminal))
    validate_parents(meta, completed)
    return dict(
        schema="common-bank-selection-protocol-v1",
        policy=POLICY,
        metadata=meta,
        completed_diagnostic=completed,
        output=str(Path(output).resolve()),
        fitting_module=fitting_module,
        sources=scientific_sources(fitting_module),
    )


def validate_protocol(path):
    frozen = json.loads(Path(path).read_bytes())
    if (
        frozen["schema"] != "common-bank-selection-protocol-v1"
        or frozen["policy"] != POLICY
        or frozen["sources"] != scientific_sources(frozen["fitting_module"])
    ):
        raise ValueError("Frozen common-bank selection rule/source changed")
    manifest, membership, parent = validate_parents(
        frozen["metadata"], frozen["completed_diagnostic"]
    )
    return frozen, manifest, membership, parent


def screen_state(case, winner, arm, *, guard, progress, progress_port=lambda numbers: None):
    """Original physical state/current bank, with an additional weight tangent only."""
    model, base = case["model"], case["model"].base
    obs, fit = base.native_observations, winner["fit"]
    vector, nuisance = np.asarray(fit["vector"]), np.asarray(fit["nuisance"])
    if (
        vector.shape != (model.size,)
        or nuisance.shape != model.initial_nuisance.shape
        or not np.isfinite(vector).all()
        or not np.isfinite(nuisance).all()
        or (arm == "zero-c" and vector[6] != 0)
        or fit["training_high_fractions"] != list(model.frame.high_fractions)
        or fit["group_receivers"] != list(model.frame.receivers)
    ):
        raise ValueError("Original saved state/frame differs")
    rows, slots = base.native_rows, base.native_slots
    guard()
    pred, visible, spatial, timing = original.predict_orbits(
        model.bank,
        obs,
        model.prior,
        vector[:2],
        vector[7] + model.basis @ vector[8:],
    )
    correction = (
        base.native_design @ vector[2:7] + base.baseline[rows] + model.group_design[rows] @ nuisance
    )
    terms = original.singleton_native_terms(
        obs.measured_hz,
        pred + correction[:, None],
        visible,
        rows,
        slots,
        base.metadata_log_emission_prior,
        base.initial,
        sigma_hz=model.score.sigma_hz,
        sample_rate_hz=base.sample_rate_hz,
    )
    if not np.isclose(terms.nll, fit["likelihood_nll"], atol=1e-7, rtol=0):
        raise ValueError("Original likelihood replay differs")
    calibration = np.column_stack([base.native_design, model.group_design[rows]])
    keep = [i for i in range(calibration.shape[1]) if arm != "zero-c" or i != 4]
    active, active_cal = original.active_constraints(model, vector, nuisance, winner["seed"])
    active_nuisance = tuple(keep.index(i) for i in active_cal if i in keep)
    if "common_timing" in active:
        active_nuisance += (len(keep),)
    geo, physical = original.window_parameter_scores(
        rows,
        terms.log_prediction_weight,
        spatial,
        timing,
        calibration[:, keep],
        model.basis,
        windows=len(model.observations.window_ids),
    )
    satellite = np.zeros((len(model.observations.window_ids), len(model.bank.numbers)))
    np.add.at(satellite, rows, terms.posterior)  # Sum alternatives; do not divide by residual.
    scores = np.empty((len(satellite), len(case["omitted"])))
    for start in range(0, len(case["omitted"]), POLICY["omitted_chunk"]):
        guard()
        ids = case["omitted"][start : start + POLICY["omitted_chunk"]]
        bank = case["full_bank"].select(ids)
        pred, visible, _, _ = original.predict_orbits(
            bank,
            obs,
            model.prior,
            vector[:2],
            np.full(len(ids), vector[7]),
            derivatives=False,
        )
        density = original.omitted_native_density(
            obs.measured_hz,
            pred + correction[:, None],
            visible,
            rows,
            base.metadata_candidate_prior[rows, slots],
            windows=len(satellite),
            sigma_hz=model.score.sigma_hz,
            sample_rate_hz=base.sample_rate_hz,
        )
        scores[:, start : start + len(ids)] = original.omitted_component_scores(
            terms.current_signal_density,
            density,
            signal_mass=terms.signal_mass,
            clutter_density=terms.clutter_density,
        )
        progress.extend(bank.numbers.tolist())
        progress_port(progress)
    guard()
    profile = project_with_weight_tangents(
        scores, geo, physical, satellite, active_nuisance_bounds=active_nuisance
    )
    guard()
    return dict(
        state="complete",
        coverage_complete=True,
        optimizer_calls=0,
        winner_start=winner["start"],
        likelihood_nll=terms.nll,
        weight_columns=profile.weight_columns,
        physical_columns=2 + physical.shape[1],
        windows=len(satellite),
        c_column_free=arm == "fitted-c",
        active_constraints=active,
        numerical_zero=list(profile.numerical_zero),
        relative_zero_tolerance=profile.relative_zero_tolerance,
        omitted=original.grouped_scores(
            profile.projection, progress, model.observations, case["block_seconds"]
        ),
    )


def make_pool(metadata_case, states, frozen):
    original_numbers = metadata_case["proposals"]["candidate_numbers"]
    original_indices = metadata_case["proposals"]["candidate_full_indices"]
    row = dict(
        original_numbers=original_numbers,
        original_full_indices=original_indices,
        source_binding=dict(
            metadata_sha256=frozen["metadata"]["sha256"],
            bank_npz_sha256=metadata_case["discovery"]["bank_npz"]["sha256"],
            parent_diagnostic_terminal_sha256=frozen["completed_diagnostic"]["terminal"]["sha256"],
        ),
        added_numbers=[],
        added_full_indices=[],
        augmented_numbers=original_numbers,
        augmented_full_indices=original_indices,
        arms=states,
        coverage_complete=False,
    )
    if any(states.get(a, {}).get("state") != "complete" for a in ARMS):
        return dict(row, state="failed", reason="Complete two-arm screen unavailable")
    numbers = states[ARMS[0]]["omitted"]["numbers"]
    if states[ARMS[1]]["omitted"]["numbers"] != numbers:
        raise ValueError("Common arms require identical full omitted catalogue order")
    inventories = [
        {
            name: [(g["group"], g["windows"]) for g in groups]
            for name, groups in states[arm]["omitted"]["groups"].items()
        }
        for arm in ARMS
    ]
    if inventories[0] != inventories[1]:
        raise ValueError("Both arms require identical original receiver/block inventory")
    result = select_common_grouped_pool(
        np.asarray(numbers, int),
        {a: states[a]["omitted"] for a in ARMS},
        {a: np.asarray(states[a]["numerical_zero"], bool) for a in ARMS},
        coverage_complete=True,
    )
    receipt = original.read_bound(metadata_case["discovery"]["bank_json"])
    full = receipt["build"]["retained_numbers"]
    by_number = {n: i for i, n in enumerate(full)}
    added = result["added_numbers"]
    indices = [by_number[n] for n in added]
    row.update(result)
    row.update(
        added_full_indices=indices,
        augmented_numbers=original_numbers + added,
        augmented_full_indices=original_indices + indices,
    )
    return row


def validate_terminal(terminal, frozen, manifest, parent):
    if (
        terminal["schema"] != "common-bank-selection-v1"
        or terminal["optimizer_calls"] != 0
        or set(terminal["cases"]) != set(LABELS)
        or not terminal["coverage_complete"]
    ):
        raise ValueError("Complete sealed selection coverage required")
    for label in LABELS:
        row = terminal["cases"][label]
        for arm in ARMS:
            state = row["arms"][arm]
            reference = parent["results"][label][arm]
            if (
                state["state"] != "complete"
                or not state["coverage_complete"]
                or state["omitted"]["numbers"] != reference["omitted"]["numbers"]
                or state["winner_start"] != reference["winner_start"]
                or state["weight_columns"] != len(row["original_numbers"]) - 1
                or state["physical_columns"] != len(reference["basis"])
                or state["c_column_free"] != (arm == "fitted-c")
            ):
                raise ValueError("Full original-state/arm/tangent coverage differs")
            space = state["omitted"]["all_parameter_space"]
            tolerance = max(
                space["rank_tolerance"],
                max(state["windows"], state["physical_columns"] + state["weight_columns"])
                * np.finfo(float).eps,
            )
            zero = [
                x is None or x <= tolerance for x in state["omitted"]["projected_norm_fraction"]
            ]
            if state["relative_zero_tolerance"] != tolerance or state["numerical_zero"] != zero:
                raise ValueError("Declared numerical-zero convention differs")
        if row != make_pool(manifest["cases"][label], row["arms"], frozen):
            raise ValueError("Selection bank/ranking/eligibility differs from frozen rule")


def validate_selection_receipt(protocol_binding, terminal_binding):
    if digest(Path(protocol_binding["path"])) != protocol_binding["sha256"]:
        raise ValueError("Selection protocol seal changed")
    frozen, manifest, _, parent = validate_protocol(protocol_binding["path"])
    terminal = original.read_bound(terminal_binding)
    if terminal["protocol_sha256"] != protocol_binding["sha256"]:
        raise ValueError("Selection terminal belongs to another protocol")
    validate_terminal(terminal, frozen, manifest, parent)
    return frozen, terminal


def run(protocol_path):
    started = time.monotonic()
    frozen, manifest, membership, parent = validate_protocol(protocol_path)
    output, sha = Path(frozen["output"]), digest(Path(protocol_path))
    terminal_path = output / "terminal.json"
    if terminal_path.exists():
        terminal = original.read_bound(binding(terminal_path))
        if terminal["protocol_sha256"] != sha:
            raise ValueError("Selection cache belongs to another freeze")
        validate_terminal(terminal, frozen, manifest, parent)
        return terminal
    if (output / "started.json").exists():
        raise ValueError("Selection slice already started; no automatic replay")
    immutable(output / "protocol.json", frozen)
    immutable(output / "started.json", dict(protocol_sha256=sha, optimizer_calls=0))
    states, current, progress = {}, None, []

    def guard():
        if time.monotonic() - started >= POLICY["calculation_seconds"]:
            raise TimeoutError("Fixed selection calculation budget exhausted")

    try:
        with bounded(max(0.001, POLICY["internal_seconds"] - (time.monotonic() - started))):
            for label in LABELS:
                current, progress = (label, None), []
                states[label] = {}
                guard()
                case = original.training_case(manifest["cases"][label], membership)
                winners = original.select_training_winners(manifest["cases"][label])
                for arm in ARMS:
                    current, progress = (label, arm), []
                    winner = winners[arm]
                    if winner is None:
                        raise ValueError("Original stationary winner unavailable; no fallback")
                    winner["seed"] = original.read_bound(
                        manifest["cases"][label]["seeds"][f"all-{winner['start']}.json"]
                    )

                    def save_progress(numbers, label=label, arm=arm):
                        immutable(
                            output / "progress" / f"{label}-{arm}-{len(numbers)}.json",
                            dict(
                                protocol_sha256=sha,
                                completed_numbers=numbers,
                                coverage_complete=False,
                                partial_selection=False,
                                optimizer_calls=0,
                            ),
                        )

                    state = screen_state(
                        case,
                        winner,
                        arm,
                        guard=guard,
                        progress=progress,
                        progress_port=save_progress,
                    )
                    states[label][arm] = state
                    immutable(
                        output / "states" / f"{label}-{arm}.json",
                        dict(protocol_sha256=sha, result=state),
                    )
    except (TimeoutError, ValueError) as error:
        if current:
            label, arm = current
            for failed_arm in ARMS if arm is None else (arm,):
                states.setdefault(label, {})[failed_arm] = dict(
                    state="failed",
                    reason=str(error),
                    coverage_complete=False,
                    completed_numbers=progress,
                    partial_selection=False,
                    optimizer_calls=0,
                )
    cases = {
        label: make_pool(manifest["cases"][label], states.get(label, {}), frozen)
        for label in LABELS
    }
    validate_protocol(protocol_path)
    complete = all(r["coverage_complete"] for r in cases.values())
    terminal = dict(
        schema="common-bank-selection-v1",
        protocol_sha256=sha,
        cases=cases,
        state="complete" if complete else "incomplete",
        coverage_complete=complete,
        optimizer_calls=0,
        elapsed_s=time.monotonic() - started,
        held_scoring=False,
        reference_usage="none",
    )
    if complete:
        validate_terminal(terminal, frozen, manifest, parent)
    immutable(terminal_path, terminal)
    return terminal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--diagnostic-protocol", type=Path)
    parser.add_argument("--diagnostic-terminal", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fitting-module", default="ds21_joint_bank_augmentation")
    args = parser.parse_args()
    if args.command == "freeze":
        if any(
            getattr(args, k) is None
            for k in ("metadata", "diagnostic_protocol", "diagnostic_terminal", "output")
        ):
            parser.error("freeze requires metadata, completed diagnostic bindings and output")
        immutable(
            args.protocol,
            draft_protocol(
                args.metadata,
                args.diagnostic_protocol,
                args.diagnostic_terminal,
                args.output,
                args.fitting_module,
            ),
        )
        result = dict(state="frozen", optimizer_calls=0)
    else:
        receipt = run(args.protocol)
        result = {
            k: receipt[k] for k in ("state", "coverage_complete", "elapsed_s", "optimizer_calls")
        }
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
