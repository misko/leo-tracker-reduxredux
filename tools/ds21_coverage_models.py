"""Original fitted-c A/B/C ports with qualified coverage-initializer authority."""

import argparse
import json
import time
from pathlib import Path

import ds21_coverage_initialization as pool
import ds21_fitted_model_receipts as receipts
import ds21_fitted_models_v2 as numerical
import numpy as np
from ds21_common import immutable, json_value

original = numerical.original
binding, read, read_bound = original.binding, original.read, original.read_bound
VIEWS, UNITS = original.VIEWS, original.UNITS
POLICY = dict(
    numerical.POLICY,
    schema="ds21-coverage-fitted-model-composition-v1",
    parent_schema="ds21-coverage-fitted-initialization-v1",
    metadata_review=receipts.POLICY,
)
INPUTS = (
    "prepared",
    "partition",
    "prior",
    "training_frames",
    "candidate_numbers",
    "candidate_full_indices",
    "proposals",
)


def sources():
    return {
        **receipts.sources(),
        **pool.sources(),
        str(Path(__file__).resolve()): binding(__file__)["sha256"],
    }


def freeze(directory, *, parent_directory):
    directory, parent_directory = Path(directory).resolve(), Path(parent_directory).resolve()
    if (directory / "protocol.json").exists():
        frozen = read_control(directory)[0]
        if frozen["parent_directory"] != str(parent_directory):
            raise ValueError("Existing qualified model parent differs")
        return frozen
    parent = pool.read_stage(parent_directory, "six-proposals")
    src = sources()
    value = dict(
        policy=POLICY,
        label=parent["frozen"]["policy"]["label"],
        parent_directory=str(parent_directory),
        parent_authority=parent["authority"],
        case_protocol=binding(parent["case_directory"] / "protocol.json"),
        coverage_terminal=parent["frozen"]["coverage_terminal"],
        inputs={k: parent["frozen"][k] for k in INPUTS},
        source_sha256=src,
        snapshot_paths=original.discovery.archive_sources(directory, src),
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "protocol.json", value)
    return read_control(directory)[0]


def read_control(directory):
    directory = Path(directory).resolve()
    frozen = read(directory / "protocol.json")
    if (
        frozen["policy"] != POLICY
        or frozen["reference_usage"] != "none"
        or frozen["held_usage"] != "none"
        or set(frozen["inputs"]) != set(INPUTS)
    ):
        raise ValueError("Qualified model policy changed")
    pool.original.shape_parent.validate_archives(directory, frozen)
    if sources() != frozen["source_sha256"]:
        raise ValueError("Qualified model scientific source closure changed")
    parent = pool.read_stage(frozen["parent_directory"], "six-proposals")
    if (
        parent["authority"] != frozen["parent_authority"]
        or binding(parent["case_directory"] / "protocol.json") != frozen["case_protocol"]
        or parent["frozen"]["coverage_terminal"] != frozen["coverage_terminal"]
        or parent["frozen"]["policy"]["label"] != frozen["label"]
        or any(parent["frozen"][k] != v for k, v in frozen["inputs"].items())
    ):
        raise ValueError("Qualified model physical parent/case authority changed")
    return frozen, parent


def initialize(directory, *, maximum_seconds=90):
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 90:
        raise ValueError("Original initialization bound must be <=90 seconds")
    directory = Path(directory).resolve()
    begun = time.monotonic()
    frozen, parent = read_control(directory)
    if (directory / "initialization.json").exists():
        return original.initialization(directory, frozen)
    if any(
        (directory / n).exists()
        for n in ("initialization-launch.json", "initialization-termination.json")
    ):
        raise ValueError("Orphan/failed qualified initialization; no retry")
    identity = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        optimizer_calls=0,
    )
    immutable(directory / "initialization-launch.json", identity)
    status = dict(identity, state="failed")
    try:
        with original.discovery.slice_bound(
            max(0.001, maximum_seconds - (time.monotonic() - begun))
        ):
            case = original.training_case(parent)
            models = original.models_for(case)
            entries = {v: read_bound(parent["authority"][f"seeds/{v}.json"]) for v in VIEWS}
            lifts = [
                original.joint.physical_receiver_branches(
                    models["C"]["all"],
                    original.native_proposals.physical_seed(
                        models["C"]["all"], e, original.evaluate_physical_correction
                    ),
                )
                for e in entries["all"]
            ]
            starts, meta = {}, {}
            for name in ("A", "B", "C"):
                starts[name], meta[name] = {}, {}
                for view in VIEWS:
                    model = models[name][view]
                    meta[name][view] = original.metadata(model, case["prepared"][view])
                    starts[name][view] = []
                    for i, e in enumerate(entries[view]):
                        if name == "C":
                            seed = original.native_proposals.proposal_start(
                                model, e, lifts[i], view=view, index=i
                            )
                        elif name == "A" and view != "low":
                            seed = numerical.unused_seed(e, model, view)
                        else:
                            seed = numerical.seed_for(e, model)
                        row = dict(
                            start=i,
                            proposal_id=original.PROPOSAL_IDS[i],
                            proposal=e,
                            seed=seed,
                            local_center=e["point_km"],
                        )
                        if name == "C":
                            row["receiver_lifts"] = lifts[i]
                        starts[name][view].append(row)
            read_control(directory)
            immutable(
                directory / "initialization.json",
                dict(
                    identity,
                    starts=starts,
                    models=meta,
                    receiver_lifts=lifts,
                    lift_derivations=6,
                    reference_usage="none",
                    held_usage="none",
                    calibration_initialization=POLICY["calibration_initialization"],
                    unused_A_initialization=POLICY["unused_A_initialization"],
                ),
            )
            status = dict(identity, initialization=binding(directory / "initialization.json"))
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(directory / "initialization-termination.json", status)
    return original.initialization(directory, frozen)


def sealed_unit(directory, unit, frozen):
    return receipts.validate_unit(directory, unit, frozen)[0]


def run_slice(directory, unit, *, slice_id, maximum_seconds=None):
    name, view, names = original.unit_spec(unit)
    cap = 90 if name == "A" else 165
    maximum_seconds = cap if maximum_seconds is None else maximum_seconds
    if (
        type(slice_id) is not int
        or slice_id < 0
        or not np.isfinite(maximum_seconds)
        or not 0 < maximum_seconds <= cap
    ):
        raise ValueError("Explicit numbered slice and original model budget required")
    directory = Path(directory).resolve()
    begun = time.monotonic()
    frozen, parent = read_control(directory)
    folder, sha = directory / "units" / unit, binding(directory / "protocol.json")["sha256"]
    if (folder / "finalized-failure.json").exists():
        return sealed_unit(directory, unit, frozen)
    initial = original.initialization(directory, frozen)
    rows = original.calls(directory, unit, sha)
    original.slices(folder, sha, unit)
    if (folder / "terminal.json").exists():
        return sealed_unit(directory, unit, frozen)
    launch = folder / "slices" / f"{slice_id:03d}-launch.json"
    launch.parent.mkdir(parents=True, exist_ok=True)
    identity = dict(protocol_sha256=sha, unit=unit, slice_id=slice_id)
    with launch.open("x") as stream:
        json.dump(identity, stream)
    status = dict(identity, state="failed")
    try:
        with original.discovery.slice_bound(
            max(0.001, maximum_seconds - (time.monotonic() - begun))
        ):
            case = original.training_case(parent)
            models = original.models_for(case)
            if {
                m: {v: original.metadata(models[m][v], case["prepared"][v]) for v in VIEWS}
                for m in models
            } != initial["models"]:
                raise ValueError("Qualified training model layout changed")
            stage_values = {}

            def stage_fit(key, model, vector, nuisance, options):
                index = int(view) if name == "A" else int(key)
                center = frozen["inputs"]["proposals"][index]["point_km"]
                call_identity = dict(protocol_sha256=sha, unit=unit, call=key, arm="fitted-c")
                expected = dict(
                    options=options,
                    seed=dict(vector=json_value(vector), nuisance=json_value(nuisance)),
                    local_center=center,
                    parameter_count=model.size,
                    nuisance_count=len(model.initial_nuisance),
                    start=index,
                )
                if key not in rows:
                    if time.monotonic() - begun + 20 >= maximum_seconds:
                        raise original.DiscoverySliceExpired(key)
                    path = folder / "calls" / f"{key}.json"
                    immutable(folder / "launches" / path.name, call_identity)
                    try:
                        fit = original.fit_group_calibration(
                            model,
                            np.array(vector, float, copy=True),
                            np.array(nuisance, float, copy=True),
                            **options,
                        )
                    except (ValueError, TimeoutError) as error:
                        fit = dict(
                            converged=False, error_type=type(error).__name__, reason=str(error)
                        )
                    row = dict(
                        call_identity,
                        **expected,
                        fit=fit,
                        stationary=original.transfer.stationary(
                            fit, center, model.size, len(model.initial_nuisance)
                        ),
                    )
                    immutable(path, row)
                    immutable(
                        folder / "terminations" / path.name,
                        dict(call_identity, call_receipt=binding(path)),
                    )
                    rows[key] = read(path)
                    print(
                        json.dumps(
                            dict(
                                label=frozen["label"],
                                unit=unit,
                                call=key,
                                stationary=rows[key]["stationary"],
                            )
                        ),
                        flush=True,
                    )
                row = rows[key]
                if any(row[k] != json_value(v) for k, v in expected.items()):
                    raise ValueError("Cached qualified physical seed/options/center changed")
                stage_values[key] = dict(row["fit"], converged=row["stationary"])
                if name == "A" and key == "final" and not row["stationary"]:
                    raise original.FinalStageUnavailable()
                return stage_values[key]

            options = dict(arm="fitted-c", seconds=20, iterations=600, local_radius_km=25)
            path_receipt, diagnostic = None, None
            if name == "A":
                starts = {v: initial["starts"]["A"][v][int(view)] for v in VIEWS}
                high_base = original.objective(
                    case["prepared"]["high"],
                    case["bank"],
                    case["prior"],
                    case["nodes"],
                    common_clock=False,
                ).base
                try:
                    path = original.fit_sequential_path(
                        models["A"]["low"],
                        high_base,
                        models["B"]["all"].base,
                        *(np.asarray(starts[v]["seed"]["vector"]) for v in ("low", "high", "all")),
                        low_nuisance=np.asarray(starts["low"]["seed"]["nuisance"]),
                        high_correction_seed=original.decode_physical_correction(
                            starts["high"]["proposal"]
                        ),
                        local_center=starts["low"]["local_center"],
                        stage_fit=stage_fit,
                        **options,
                    )
                except original.FinalStageUnavailable:
                    path = dict(status="final-nonstationary", **stage_values)
                path_receipt = json_value(
                    {k: v for k, v in path.items() if k not in ("frozen", "shift", "final_model")}
                )
                if "shift" in path:
                    path_receipt.update(
                        fixed_shift_receivers=list(path["shift"].receivers),
                        fixed_shift_hz=path["shift"].offsets_hz.tolist(),
                    )
                winner = rows.get("final") if path["status"] == "complete" else None
                if winner is not None:
                    diagnostic = original.diagnose("A", path["final_model"], winner["fit"])
            else:
                model = models[name][view]
                for key in names:
                    start = initial["starts"][name][view][int(key)]
                    stage_fit(
                        key,
                        model,
                        np.asarray(start["seed"]["vector"]),
                        np.asarray(start["seed"]["nuisance"]),
                        dict(options, local_center=start["local_center"]),
                    )
                winner = original.select(list(rows.values()))
                if winner is not None:
                    if name == "B":
                        original.freeze_group_calibration(model, winner["fit"])
                    diagnostic = original.diagnose(name, model, winner["fit"])
            read_control(directory)
            immutable(
                folder / "terminal.json",
                dict(
                    protocol_sha256=sha,
                    label=frozen["label"],
                    unit=unit,
                    state="complete",
                    initialization=binding(directory / "initialization.json"),
                    calls=rows,
                    optimizer_calls=len(rows),
                    skipped_calls=[k for k in names if k not in rows],
                    path=path_receipt,
                    selection=winner,
                    diagnostics=diagnostic,
                    reference_usage="none",
                    held_usage="none",
                ),
            )
            status["state"] = "complete"
    except original.DiscoverySliceExpired as error:
        status.update(state="checkpointed", next_call=str(error))
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(launch.with_name(launch.name.replace("-launch", "-termination")), status)
    return (
        dict(status, optimizer_calls=len(rows))
        if status["state"] == "checkpointed"
        else sealed_unit(directory, unit, frozen)
    )


def finalize_failure(directory, unit, *, reason, process_terminal_confirmed=False):
    original.unit_spec(unit)
    directory = Path(directory).resolve()
    frozen, _ = read_control(directory)
    folder = directory / "units" / unit
    if process_terminal_confirmed is not True or not isinstance(reason, str) or not reason.strip():
        raise ValueError("Verified terminal process and explicit failure reason required")
    if (folder / "terminal.json").exists():
        raise ValueError("Success/failure outcome coexistence refused")
    immutable(
        folder / "finalized-failure.json",
        dict(
            state="finalized-failure",
            label=frozen["label"],
            unit=unit,
            reason=reason,
            process_terminal_confirmed=True,
            protocol_sha256=binding(directory / "protocol.json")["sha256"],
            inventory=original.failure_inventory(directory, unit),
            reference_usage="none",
            held_usage="none",
        ),
    )
    return sealed_unit(directory, unit, frozen)


def seal(directory):
    directory = Path(directory).resolve()
    frozen, _ = read_control(directory)
    outcomes = {u: sealed_unit(directory, u, frozen) for u in UNITS}
    selections = {
        "A-all": original.select(
            [
                o["selection"]
                for u, o in outcomes.items()
                if u.startswith("A-") and o["state"] == "complete" and o["selection"] is not None
            ]
        )
    }
    selections.update(
        {u: o.get("selection") for u, o in outcomes.items() if not u.startswith("A-")}
    )
    count = sum(
        o.get("optimizer_calls", sum(1 for p in o.get("inventory", {}) if "/launches/" in p))
        for o in outcomes.values()
    )
    if count > 54:
        raise ValueError("Original 54-call maximum exceeded")
    value = dict(
        label=frozen["label"],
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        outcomes=outcomes,
        selections=selections,
        optimizer_calls=count,
        maximum_optimizer_calls=54,
        terminals={
            u: binding(
                directory
                / "units"
                / u
                / ("terminal.json" if o["state"] == "complete" else "finalized-failure.json")
            )
            for u, o in outcomes.items()
        },
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "terminal.json", value)
    return read(directory / "terminal.json")


def evaluate(directory):
    directory = Path(directory).resolve()
    terminal = seal(directory)
    frozen, _ = read_control(directory)
    from ds21_evaluate import coordinates, distance_km, reference

    from leo.contracts.regional_position import RegionalPrior

    expected, rows, prior = reference(), [], RegionalPrior(**frozen["inputs"]["prior"])
    for key, winner in terminal["selections"].items():
        name, view = key.split("-")
        row = dict(model=name, view=view, state="unavailable", below_0_5km=False)
        if winner is not None:
            location = coordinates(prior, winner["fit"]["vector"][:2])
            error = distance_km(location, expected)
            row.update(
                state="estimated",
                start=winner["start"],
                proposal_id=original.PROPOSAL_IDS[winner["start"]],
                coordinates_deg=list(location),
                error_km=error,
                below_0_5km=error < 0.5,
                common_c_hz_per_ghz=winner["fit"]["vector"][6],
            )
        rows.append(row)
    value = dict(
        label=frozen["label"],
        arm="fitted-c",
        rows=rows,
        terminal=binding(directory / "terminal.json"),
        evaluator=binding(__file__),
        reference_usage="After all twelve qualified scientific outcomes sealed",
        limitation="; ".join(POLICY[k] for k in ["A_scope", "half_view_limitation", "C_limitation"])
        + "; configured reference, not independently surveyed",
        calibration_initialization=POLICY["calibration_initialization"],
    )
    immutable(directory / "development-errors.json", value)
    return read(directory / "development-errors.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("freeze", "initialize", "run-slice", "seal", "evaluate", "finalize-failure"),
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--parent-directory", type=Path)
    parser.add_argument("--unit", choices=UNITS)
    parser.add_argument("--slice-id", type=int)
    parser.add_argument("--maximum-seconds", type=float)
    parser.add_argument("--reason")
    parser.add_argument("--process-terminal-confirmed", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        if args.parent_directory is None:
            parser.error("freeze requires --parent-directory")
        result = freeze(args.directory, parent_directory=args.parent_directory)
    elif args.command == "initialize":
        result = initialize(
            args.directory,
            maximum_seconds=90 if args.maximum_seconds is None else args.maximum_seconds,
        )
    elif args.command == "run-slice":
        if args.unit is None or args.slice_id is None:
            parser.error("run-slice requires --unit and --slice-id")
        result = run_slice(
            args.directory, args.unit, slice_id=args.slice_id, maximum_seconds=args.maximum_seconds
        )
    elif args.command == "finalize-failure":
        if args.unit is None or args.reason is None:
            parser.error("finalize-failure requires --unit and --reason")
        result = finalize_failure(
            args.directory,
            args.unit,
            reason=args.reason,
            process_terminal_confirmed=args.process_terminal_confirmed,
        )
    else:
        result = seal(args.directory) if args.command == "seal" else evaluate(args.directory)
    print(json.dumps(json_value(result), allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
