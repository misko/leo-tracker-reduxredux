"""Original fitted-c A/B/C with independently verified exact seed transfer.

Version1 and all numerical cores stay immutable. Exact-compatible saved initial
coefficients are reused only after checking their physical function and every
fitter bound. Other cases retain the original strict bounded projection. No
failed solver result is accepted as a fit or as a calibration projection.
"""

import argparse
import json
import time
from pathlib import Path

import ds21_fitted_models as original
import numpy as np
from ds21_common import immutable, json_value

POLICY = dict(
    original.POLICY,
    schema="ds21-generic-fitted-model-composition-v2",
    calibration_initialization=(
        "Original strict projection first; only its exact nonconvergence error may trigger "
        "independently verified feasible original source-function coefficients"
    ),
    unused_A_initialization=(
        "High consumes physical timing only; all vector is entirely overwritten "
        "by original sequential core"
    ),
    physical_closure_tolerance_hz=1e-6,
)
binding, read, read_bound = original.binding, original.read, original.read_bound
VIEWS, UNITS = original.VIEWS, original.UNITS


class ExactSeedUnavailable(ValueError):
    """The persisted source coefficient representation is not proven compatible."""


def sources():
    return {**original.sources(), str(Path(__file__).resolve()): binding(__file__)["sha256"]}


def freeze(directory, *, parent_directory):
    directory, parent_directory = Path(directory).resolve(), Path(parent_directory).resolve()
    parent = original.pool.read_stage(parent_directory, "six-proposals")
    frozen, source = parent["frozen"], sources()
    value = dict(
        policy=POLICY,
        label=frozen["policy"]["label"],
        parent_directory=str(parent_directory),
        parent_authority=parent["authority"],
        case_protocol=binding(Path(parent["case_directory"]) / "protocol.json"),
        inputs={
            k: frozen[k]
            for k in (
                "prepared",
                "partition",
                "prior",
                "training_frames",
                "candidate_numbers",
                "candidate_full_indices",
                "proposals",
            )
        },
        source_sha256=source,
        snapshot_paths=original.discovery.archive_sources(directory, source),
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
    ):
        raise ValueError("Fitted model v2 policy changed")
    original.pool.shape_parent.validate_archives(directory, frozen)
    if sources() != frozen["source_sha256"]:
        raise ValueError("Fitted model v2 source closure changed")
    parent = original.pool.read_stage(frozen["parent_directory"], "six-proposals")
    if (
        parent["authority"] != frozen["parent_authority"]
        or binding(Path(parent["case_directory"]) / "protocol.json") != frozen["case_protocol"]
        or parent["frozen"]["policy"]["label"] != frozen["label"]
        or any(parent["frozen"][k] != v for k, v in frozen["inputs"].items())
    ):
        raise ValueError("Fitted model v2 original parent changed")
    return frozen, parent


def timing_seed(entry, model):
    timing = entry["orbit_timing"]
    numbers, shifts = timing["satellite_numbers"], timing["shifts_s"]
    if (
        len(numbers) != len(set(numbers))
        or len(numbers) != len(shifts)
        or set(numbers) != set(model.bank.numbers.tolist())
    ):
        raise ValueError("Physical satellite timing identity changed")
    lookup = dict(zip(numbers, shifts, strict=True))
    values = np.array([lookup[int(n)] for n in model.bank.numbers])
    if not np.isfinite(values).all():
        raise ValueError("Finite physical timing required")
    return np.r_[values.mean(), model.basis.T @ (values - values.mean())], values


def exact_seed(entry, model):
    """Prove frame/basis/function/bounds before copying any private coefficients."""
    state = original.decode_physical_correction(entry)
    obs = model.observations
    vector, nuisance = np.asarray(entry["vector"], float), np.asarray(entry["nuisance"], float)
    if (
        vector.shape != (model.size,)
        or nuisance.shape != model.initial_nuisance.shape
        or not np.isfinite(vector).all()
        or not np.isfinite(nuisance).all()
        or state.time_center_s != obs.time_center_s
        or state.rf_center_hz != obs.rf_center_hz
        or state.frame != model.frame
        or model.drift_count
        or model.group_clock_count
    ):
        raise ExactSeedUnavailable("Source/target calibration frame or layout differs")
    clock, group = model.split(nuisance)
    nodes = model.base.nodes if model.clock_count else np.empty(0)
    knots = clock.reshape(2, -1) @ model.base.null.T if model.clock_count else np.empty((2, 0))
    if (
        not np.array_equal(state.clock_nodes_s, nodes)
        or knots.shape != state.clock_knots_hz.shape
        or np.max(abs(knots - state.clock_knots_hz), initial=0) > 1e-7
        or not np.array_equal(state.receiver_rf_coefficients, vector[2:7])
        or not np.array_equal(state.group_offsets_hz, group)
        or len(state.group_drifts_hz_s)
        or np.any(state.group_clock_knots_hz)
    ):
        raise ExactSeedUnavailable("Source/target clock basis or functional coefficients differ")
    dt = obs.times_s - obs.time_center_s
    baseline = state.baseline_affine[obs.receiver, 0] + state.baseline_affine[obs.receiver, 1] * dt
    if (
        np.max(abs(baseline - model.base.baseline), initial=0)
        > POLICY["physical_closure_tolerance_hz"]
    ):
        raise ExactSeedUnavailable("Source/target physical baseline differs")
    limits = np.r_[np.full(model.clock_count, 2000.0), model.group_limits]
    if (
        np.any(abs(vector[[3, 5]]) > 60)
        or abs(vector[6]) > 5000
        or np.any(abs(nuisance) > limits)
        or np.linalg.norm(vector[:2]) > model.prior.radius_km + 1e-9
        or vector[:2].tolist() != entry["point_km"]
    ):
        raise ExactSeedUnavailable("Source calibration or geography outside original bounds")
    timing, shifts = timing_seed(entry, model)
    coverage_min = float(model.bank.nodes_s[0] - obs.times_s.min())
    coverage_max = float(model.bank.nodes_s[-1] - obs.times_s.max())
    minimum, maximum = max(-20.0, coverage_min), min(20.0, coverage_max)
    if not coverage_min < minimum < 0 < maximum < coverage_max:
        raise ExactSeedUnavailable("Original strict orbit interpolation margin required")
    if abs(timing[0]) > 10 or np.any(shifts < minimum) or np.any(shifts > maximum):
        raise ExactSeedUnavailable("Source timing outside original bounds")
    vector = vector.copy()
    vector[7:] = timing
    expected = original.evaluate_physical_correction(entry, obs)
    actual = model.correction(vector, nuisance)
    residual = actual - expected
    maximum_error = float(np.max(abs(residual), initial=0))
    if not np.isfinite(actual).all() or maximum_error > POLICY["physical_closure_tolerance_hz"]:
        raise ExactSeedUnavailable("Exact source transfer fails independent physical closure")
    coefficients = np.r_[vector[2:7], nuisance]
    lower = np.r_[-np.inf, -60.0, -np.inf, -60.0, -5000.0, -limits]
    upper = np.r_[np.inf, 60.0, np.inf, 60.0, 5000.0, limits]
    return dict(
        vector=vector,
        nuisance=nuisance.copy(),
        proposal_id=entry["proposal_id"],
        id=entry.get("id", entry["proposal_id"]),
        projection=dict(
            method="exact-feasible-source-transfer",
            coefficients=coefficients,
            rms_hz=float(np.sqrt(np.mean(residual**2))),
            maximum_abs_hz=maximum_error,
            active_bounds=np.flatnonzero(
                (coefficients == lower) | (coefficients == upper)
            ).tolist(),
            frame_verified=True,
            clock_basis_verified=True,
            coefficient_bounds_verified=True,
            timing_bounds_verified=True,
            location_fit=False,
        ),
    )


def seed_for(entry, model):
    try:
        result = original.project_shared_seed(entry, model)
        return {
            **result,
            "projection": {
                **result["projection"],
                "method": "original-strict-bounded-projection",
            },
        }
    except ValueError as error:
        if str(error) != "bounded carried-calibration projection did not converge":
            raise
        result = exact_seed(entry, model)
        result["projection"]["strict_projection_error"] = str(error)
        return result


def unused_seed(entry, model, view):
    timing, _ = timing_seed(entry, model)
    return dict(
        vector=np.r_[entry["point_km"], np.zeros(5), timing],
        nuisance=np.zeros_like(model.initial_nuisance),
        proposal_id=entry["proposal_id"],
        projection=dict(
            method="unused-initial-calibration",
            consumed_coordinates="timing only" if view == "high" else "none",
            location_fit=False,
        ),
    )


def initialize(directory, *, maximum_seconds=90):
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 90:
        raise ValueError("Initialization bound must be <=90 seconds")
    directory = Path(directory).resolve()
    begun = time.monotonic()
    frozen, parent = read_control(directory)
    if (directory / "initialization.json").exists():
        return original.initialization(directory, frozen)
    if any(
        (directory / n).exists()
        for n in ("initialization-launch.json", "initialization-termination.json")
    ):
        raise ValueError("Orphan/failed v2 initialization; no retry")
    identity = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        optimizer_calls=0,
    )
    immutable(directory / "initialization-launch.json", identity)
    status = dict(**identity, state="failed")
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
                            seed = unused_seed(e, model, view)
                        else:
                            seed = seed_for(e, model)
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
                    **identity,
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
            status = dict(**identity, initialization=binding(directory / "initialization.json"))
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(directory / "initialization-termination.json", status)
    return original.initialization(directory, frozen)


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
        raise ValueError("Explicit slice id and original bounded slice required")
    directory = Path(directory).resolve()
    begun = time.monotonic()
    frozen, parent = read_control(directory)
    folder, sha = directory / "units" / unit, binding(directory / "protocol.json")["sha256"]
    if (folder / "finalized-failure.json").exists():
        return original.sealed_unit(directory, unit, frozen)
    initial = original.initialization(directory, frozen)
    rows = original.calls(directory, unit, sha)
    original.slices(folder, sha, unit)
    if (folder / "terminal.json").exists():
        return original.sealed_unit(directory, unit, frozen)
    launch = folder / "slices" / f"{slice_id:03d}-launch.json"
    launch.parent.mkdir(parents=True, exist_ok=True)
    identity = dict(protocol_sha256=sha, unit=unit, slice_id=slice_id)
    with launch.open("x") as stream:
        json.dump(identity, stream)
    status = dict(**identity, state="failed")
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
                raise ValueError("Fitted v2 training model layout changed")
            stage_values = {}

            def stage_fit(key, model, vector, nuisance, options):
                index = int(view) if name == "A" else int(key)
                center = frozen["inputs"]["proposals"][index]["point_km"]
                expected = dict(
                    options=options,
                    seed=dict(vector=json_value(vector), nuisance=json_value(nuisance)),
                    local_center=center,
                    parameter_count=model.size,
                    nuisance_count=len(model.initial_nuisance),
                    start=index,
                )
                claim = dict(protocol_sha256=sha, unit=unit, call=key, arm="fitted-c")
                if key not in rows:
                    if time.monotonic() - begun + 20 >= maximum_seconds:
                        raise original.DiscoverySliceExpired(key)
                    path = folder / "calls" / f"{key}.json"
                    immutable(folder / "launches" / path.name, claim)
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
                    immutable(
                        path,
                        dict(
                            **claim,
                            **expected,
                            fit=fit,
                            stationary=original.transfer.stationary(
                                fit, center, model.size, len(model.initial_nuisance)
                            ),
                        ),
                    )
                    immutable(
                        folder / "terminations" / path.name,
                        dict(**claim, call_receipt=binding(path)),
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
                    raise ValueError("Cached v2 physical seed/options/center changed")
                stage_values[key] = dict(row["fit"], converged=row["stationary"])
                if name == "A" and key == "final" and not row["stationary"]:
                    raise original.FinalStageUnavailable()
                return stage_values[key]

            options = dict(arm="fitted-c", seconds=20, iterations=600, local_radius_km=25)
            path_receipt, diagnostic = None, None
            if name == "A":
                i = int(view)
                starts = {v: initial["starts"]["A"][v][i] for v in VIEWS}
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
                        dict(**options, local_center=start["local_center"]),
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
        dict(**status, optimizer_calls=len(rows))
        if status["state"] == "checkpointed"
        else original.sealed_unit(directory, unit, frozen)
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
    return original.sealed_unit(directory, unit, frozen)


def seal(directory):
    directory = Path(directory).resolve()
    frozen, _ = read_control(directory)
    outcomes = {u: original.sealed_unit(directory, u, frozen) for u in UNITS}
    a = [
        o["selection"]
        for u, o in outcomes.items()
        if u.startswith("A-") and o["state"] == "complete" and o["selection"] is not None
    ]
    selections = {
        "A-all": original.select(a),
        **{u: o.get("selection") for u, o in outcomes.items() if not u.startswith("A-")},
    }
    value = dict(
        label=frozen["label"],
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        outcomes=outcomes,
        selections=selections,
        optimizer_calls=sum(
            o.get("optimizer_calls", sum(1 for p in o.get("inventory", {}) if "/launches/" in p))
            for o in outcomes.values()
        ),
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
    frozen = read(directory / "protocol.json")
    from ds21_evaluate import coordinates, distance_km, reference

    from leo.contracts.regional_position import RegionalPrior

    expected, rows, prior = reference(), [], RegionalPrior(**frozen["inputs"]["prior"])
    for key, winner in terminal["selections"].items():
        name, view = key.split("-")
        row = dict(model=name, view=view, state="unavailable", below_0_5km=False)
        if winner is not None:
            point = coordinates(prior, winner["fit"]["vector"][:2])
            error = distance_km(point, expected)
            row.update(
                state="estimated",
                start=winner["start"],
                proposal_id=original.PROPOSAL_IDS[winner["start"]],
                coordinates_deg=list(point),
                error_km=error,
                below_0_5km=error < 0.5,
                common_c_hz_per_ghz=winner["fit"]["vector"][6],
            )
        rows.append(row)
    immutable(
        directory / "development-errors.json",
        dict(
            label=frozen["label"],
            arm="fitted-c",
            rows=rows,
            terminal=binding(directory / "terminal.json"),
            evaluator=binding(__file__),
            reference_usage="After all twelve original model outcomes sealed",
            limitation=POLICY["A_scope"]
            + "; "
            + POLICY["half_view_limitation"]
            + "; "
            + POLICY["C_limitation"],
            calibration_initialization=POLICY["calibration_initialization"],
        ),
    )
    return read(directory / "development-errors.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("freeze", "initialize", "run-slice", "seal", "evaluate")
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--parent-directory", type=Path)
    parser.add_argument("--unit", choices=UNITS)
    parser.add_argument("--slice-id", type=int)
    parser.add_argument("--maximum-seconds", type=float)
    args = parser.parse_args()
    if args.command == "freeze":
        if args.parent_directory is None:
            parser.error("--parent-directory required")
        result = freeze(args.directory, parent_directory=args.parent_directory)
    elif args.command == "initialize":
        result = initialize(args.directory, maximum_seconds=args.maximum_seconds or 90)
    elif args.command == "run-slice":
        if args.unit is None or args.slice_id is None:
            parser.error("--unit and --slice-id required")
        result = run_slice(
            args.directory, args.unit, slice_id=args.slice_id, maximum_seconds=args.maximum_seconds
        )
    else:
        result = seal(args.directory) if args.command == "seal" else evaluate(args.directory)
    print(
        json.dumps(
            dict(
                label=result.get("label"),
                command=args.command,
                state=result.get("state", "sealed"),
                optimizer_calls=result.get("optimizer_calls", 0),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
