"""Bounded matched A high-timing control on frozen fitted-only model parents.

No campaign or held loader is provided. Each explicit unit reuses its own
validated stationary low receipt and makes at most two new fits. The separate
reference evaluator requires all twelve units and both selectors to be sealed.
"""

import argparse
import json
import time
from pathlib import Path

import ds21_coverage_models as coverage
import ds21_fitted_model_receipts as receipt_review
import ds21_fitted_models_v2 as numerical
import numpy as np
from ds21_common import immutable, json_value

from leo.analysis import model_a_timing_locked_high as experiment

original = numerical.original
binding, read = original.binding, original.read
CONDITIONS = ("original-high-repeat", "low-timing-locked-high")
UNITS = tuple(f"{condition}-{i}" for condition in CONDITIONS for i in range(6))
POLICY = dict(
    schema="ds21-model-a-low-timing-locked-high-control-v1",
    arm="fitted-c",
    conditions=list(CONDITIONS),
    starts=6,
    fit_seconds=20,
    iterations=600,
    local_radius_km=25,
    units=list(UNITS),
    maximum_new_optimizer_calls=24,
    maximum_seconds_per_unit=90,
    external_term_seconds=105,
    external_kill_seconds=110,
    inherited_low_fits=6,
    low_stage="Reuse own original validated low fit in both conditions",
    treatment="High receiver offsets only; position/correction/timing fixed to own low fit",
    baseline="Original high timing/offset fit, then original final fit",
    final="Original fitted-c free geography/common correction/timing with fixed learned offsets",
    selection="Minimum stationary final training objective, then original start index",
    reference_usage="none",
    held_usage="none",
    failed_retry=False,
    half_view_scope="Dependent shared-initialization stages; no independent half-only claim",
)


def sources():
    return {
        **receipt_review.sources(),
        **coverage.sources(),
        str(Path(__file__).resolve()): binding(__file__)["sha256"],
        str(Path(experiment.__file__).resolve()): binding(experiment.__file__)["sha256"],
    }


def parent_provider(model_directory):
    """Dispatch qualified schemas through their genuine original readers."""
    schema = read(Path(model_directory) / "protocol.json")["policy"]["schema"]
    if schema == numerical.POLICY["schema"]:
        return numerical
    if schema == coverage.POLICY["schema"]:
        return coverage
    raise ValueError("A control requires original fitted-v2 or qualified coverage-v1 parent")


def parent_state(model_directory):
    provider = parent_provider(model_directory)
    frozen, parent = provider.read_control(model_directory)
    initial = original.initialization(model_directory, frozen)
    low = {}
    for i in range(6):
        outcome = (
            coverage.sealed_unit(model_directory, f"A-{i}", frozen)
            if provider is coverage
            else receipt_review.validate_unit(model_directory, f"A-{i}", frozen)[0]
        )
        if outcome["state"] != "complete" or "low" not in outcome["calls"]:
            raise ValueError("All six original A paths must have sealed low outcomes")
        path = Path(model_directory) / "units" / f"A-{i}" / "calls" / "low.json"
        low[str(i)] = binding(path)
    return frozen, parent, initial, low


def freeze(directory, *, model_directory):
    directory, model_directory = Path(directory).resolve(), Path(model_directory).resolve()
    if (directory / "protocol.json").exists():
        frozen = read_control(directory)[0]
        if frozen["model_directory"] != str(model_directory):
            raise ValueError("Existing A control original model parent differs")
        return frozen
    frozen, _, _, low = parent_state(model_directory)
    source = sources()
    value = dict(
        policy=POLICY,
        label=frozen["label"],
        model_directory=str(model_directory),
        model_protocol=binding(model_directory / "protocol.json"),
        initialization=binding(model_directory / "initialization.json"),
        parent_schema=frozen["policy"]["schema"],
        parent_units={
            str(i): binding(model_directory / "units" / f"A-{i}" / "terminal.json")
            for i in range(6)
        },
        inherited_low=low,
        inputs=frozen["inputs"],
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
        raise ValueError("A timing control policy changed")
    original.pool.shape_parent.validate_archives(directory, frozen)
    if sources() != frozen["source_sha256"]:
        raise ValueError("A timing control reachable sources changed")
    model_directory = Path(frozen["model_directory"])
    model, parent, initial, low = parent_state(model_directory)
    if (
        model["label"] != frozen["label"]
        or model["inputs"] != frozen["inputs"]
        or model["policy"]["schema"] != frozen["parent_schema"]
        or binding(model_directory / "protocol.json") != frozen["model_protocol"]
        or binding(model_directory / "initialization.json") != frozen["initialization"]
        or low != frozen["inherited_low"]
    ):
        raise ValueError("A timing control original parent/input/low authority changed")
    for receipt in frozen["inherited_low"].values():
        original.read_bound(receipt)
    for receipt in frozen["parent_units"].values():
        original.read_bound(receipt)
    return frozen, parent, initial


def unit_spec(unit):
    if unit not in UNITS:
        raise ValueError("Explicit predeclared A condition/start unit required")
    condition, index = unit.rsplit("-", 1)
    return condition, int(index)


def validate_terminal(directory, unit, frozen):
    """Check sealed calls without numerical model evaluation or reference access."""
    condition, index = unit_spec(unit)
    folder = Path(directory) / "units" / unit
    value = read(folder / "terminal.json")
    identity = dict(protocol_sha256=binding(Path(directory) / "protocol.json")["sha256"], unit=unit)
    if read(folder / "launch.json") != identity:
        raise ValueError("A control launch identity changed")
    if read(folder / "termination.json") != dict(
        **identity, state="complete", terminal=binding(folder / "terminal.json")
    ):
        raise ValueError("A control termination authority changed")
    low = original.read_bound(frozen["inherited_low"][str(index)])
    rows = value["calls"]
    stage_status = value["path"]["status"]
    if stage_status not in {
        "complete",
        "low-nonstationary",
        "high-nonstationary",
        "final-nonstationary",
    }:
        raise ValueError("A control unknown sequential outcome")
    names = (
        {"high", "final"}
        if stage_status in {"complete", "final-nonstationary"}
        else {"high"}
        if low["stationary"]
        else set()
    )
    if (
        value["protocol_sha256"] != identity["protocol_sha256"]
        or value["unit"] != unit
        or value["condition"] != condition
        or value["start"] != index
        or value["inherited_low"] != frozen["inherited_low"][str(index)]
        or value["optimizer_calls"] != len(rows)
        or set(rows) != names
        or value["reference_usage"] != "none"
        or value["held_usage"] != "none"
        or not value["path"]["low"] == dict(low["fit"], converged=low["stationary"])
    ):
        raise ValueError("A control path/call coverage or inherited low differs")
    for kind in ("calls", "launches", "terminations"):
        if {p.stem for p in (folder / kind).glob("*.json")} != names:
            raise ValueError("A control missing/extra/orphan stage inventory")
    for key, row in rows.items():
        path = folder / "calls" / f"{key}.json"
        claim = dict(**identity, call=key)
        if (
            row != read(path)
            or read(folder / "launches" / path.name) != claim
            or read(folder / "terminations" / path.name)
            != dict(**claim, call_receipt=binding(path))
            or row["stationary"]
            != original.transfer.stationary(
                row["fit"], row["local_center"], row["parameter_count"], row["nuisance_count"]
            )
            or any(row.get(k) != v for k, v in claim.items())
            or row["condition"] != condition
            or row["start"] != index
            or row["local_center"] != low["local_center"]
        ):
            raise ValueError("A control individual call authority changed")
        expected_options = dict(arm="fitted-c", seconds=20, iterations=600)
        if key == "high":
            expected_options["fixed_position"] = True
            if condition == CONDITIONS[1]:
                expected_options.update(fixed_timing=True, timing_source="own-low")
        else:
            expected_options.update(local_center=low["local_center"], local_radius_km=25)
        if row["options"] != expected_options:
            raise ValueError("A control fit options/domain changed")
        stage_fit = value["path"][key]
        expected_fit = dict(row["fit"], converged=row["stationary"])
        if key == "high":
            expected_fit["training_high_fractions"] = None
            if stage_fit.get("offset_parameterization") != "uncentred-high-minus-low":
                raise ValueError("A control high descriptive parameterization differs")
        if any(stage_fit.get(k) != v for k, v in expected_fit.items()):
            raise ValueError("A control saved path/call scientific fields differ")
        if (
            condition == CONDITIONS[1]
            and key == "high"
            and "vector" in row["fit"]
            and (
                row["fit"].get("fixed_timing") is not True
                or row["fit"].get("stationarity_scope")
                != "receiver-offsets-only; low-position-correction-timing-fixed"
                or row["seed"]["vector"][7:] != low["fit"]["vector"][7:]
                or row["seed"]["vector"][:2] != low["fit"]["vector"][:2]
                or row["seed"]["vector"][2:7] != [0] * 5
                or row["fit"]["vector"] != row["seed"]["vector"]
            )
        ):
            raise ValueError("A control fixed timing/certificate differs")
    winner = rows.get("final") if value["path"]["status"] == "complete" else None
    if (
        (stage_status == "low-nonstationary") != (not low["stationary"])
        or (stage_status == "high-nonstationary" and rows["high"]["stationary"])
        or (stage_status in {"complete", "final-nonstationary"} and not rows["high"]["stationary"])
        or (stage_status == "final-nonstationary" and rows["final"]["stationary"])
    ):
        raise ValueError("A control prerequisite stationarity differs")
    if value["selection"] != winner or (winner is not None and not winner["stationary"]):
        raise ValueError("A control final training selection differs")
    return value


def run_unit(directory, unit, *, maximum_seconds=90):
    condition, index = unit_spec(unit)
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 90:
        raise ValueError("A unit must be bounded to at most 90 seconds")
    begun = time.monotonic()
    directory = Path(directory).resolve()
    frozen, parent, initial = read_control(directory)
    folder = directory / "units" / unit
    if (folder / "terminal.json").exists():
        return validate_terminal(directory, unit, frozen)
    if (folder / "launch.json").exists() or (folder / "termination.json").exists():
        raise ValueError("Orphan/failed A control unit; no retry")
    identity = dict(protocol_sha256=binding(directory / "protocol.json")["sha256"], unit=unit)
    immutable(folder / "launch.json", identity)
    status = dict(**identity, state="failed")
    try:
        with original.discovery.slice_bound(
            max(0.001, maximum_seconds - (time.monotonic() - begun))
        ):
            case = original.training_case(parent)
            starts = {view: initial["starts"]["A"][view][index] for view in original.VIEWS}
            low_row = original.read_bound(frozen["inherited_low"][str(index)])
            low_model = original.objective(
                case["prepared"]["low"], case["bank"], case["prior"], case["nodes"]
            )
            high_base = original.objective(
                case["prepared"]["high"],
                case["bank"],
                case["prior"],
                case["nodes"],
                common_clock=False,
            ).base
            all_base = original.objective(
                case["prepared"]["all"], case["bank"], case["prior"], case["nodes"]
            ).base
            rows, stage_values = {}, {}

            def stage_fit(stage, model, vector, nuisance, options):
                if stage == "low":
                    if (
                        json_value(vector) != low_row["seed"]["vector"]
                        or json_value(nuisance) != low_row["seed"]["nuisance"]
                        or json_value(options) != low_row["options"]
                        or model.size != low_row["parameter_count"]
                        or len(model.initial_nuisance) != low_row["nuisance_count"]
                    ):
                        raise ValueError("Inherited low physical seed/options/layout changed")
                    return dict(low_row["fit"], converged=low_row["stationary"])
                if time.monotonic() - begun + 20 >= maximum_seconds:
                    raise TimeoutError("Insufficient bounded unit time for next stage; no retry")
                vector = np.asarray(vector, float).copy()
                locked = stage == "high" and condition == CONDITIONS[1]
                if locked:
                    vector[7:] = low_row["fit"]["vector"][7:]
                path = folder / "calls" / f"{stage}.json"
                claim = dict(**identity, call=stage)
                immutable(folder / "launches" / path.name, claim)
                try:
                    fit = (
                        experiment.fit_timing_locked_high(model, vector, nuisance)
                        if locked
                        else original.fit_group_calibration(model, vector, nuisance, **options)
                    )
                except (ValueError, TimeoutError) as error:
                    fit = dict(converged=False, error_type=type(error).__name__, reason=str(error))
                stationary = original.transfer.stationary(
                    fit, starts["low"]["local_center"], model.size, len(model.initial_nuisance)
                )
                row = dict(
                    **claim,
                    start=index,
                    condition=condition,
                    options=dict(options, fixed_timing=True, timing_source="own-low")
                    if locked
                    else options,
                    seed=dict(vector=vector, nuisance=nuisance),
                    local_center=starts["low"]["local_center"],
                    parameter_count=model.size,
                    nuisance_count=len(model.initial_nuisance),
                    fit=fit,
                    stationary=stationary,
                )
                immutable(path, row)
                immutable(
                    folder / "terminations" / path.name, dict(**claim, call_receipt=binding(path))
                )
                rows[stage] = read(path)
                stage_values[stage] = dict(rows[stage]["fit"], converged=stationary)
                if stage == "final" and not stationary:
                    raise original.FinalStageUnavailable()
                return stage_values[stage]

            try:
                path = original.fit_sequential_path(
                    low_model,
                    high_base,
                    all_base,
                    *(np.asarray(starts[v]["seed"]["vector"]) for v in ("low", "high", "all")),
                    low_nuisance=np.asarray(starts["low"]["seed"]["nuisance"]),
                    high_correction_seed=original.decode_physical_correction(
                        starts["high"]["proposal"]
                    ),
                    local_center=starts["low"]["local_center"],
                    local_radius_km=25,
                    stage_fit=stage_fit,
                    arm="fitted-c",
                    seconds=20,
                    iterations=600,
                )
            except original.FinalStageUnavailable:
                path = dict(
                    status="final-nonstationary",
                    low=dict(low_row["fit"], converged=low_row["stationary"]),
                    **stage_values,
                )
            path_receipt = {
                k: v for k, v in path.items() if k not in ("frozen", "shift", "final_model")
            }
            if "shift" in path:
                path_receipt.update(
                    fixed_shift_receivers=path["shift"].receivers,
                    fixed_shift_hz=path["shift"].offsets_hz,
                )
            read_control(directory)
            value = dict(
                **identity,
                label=frozen["label"],
                condition=condition,
                start=index,
                inherited_low=frozen["inherited_low"][str(index)],
                optimizer_calls=len(rows),
                calls=rows,
                path=path_receipt,
                selection=rows.get("final") if path["status"] == "complete" else None,
                reference_usage="none",
                held_usage="none",
            )
            immutable(folder / "terminal.json", value)
            status = dict(**identity, state="complete", terminal=binding(folder / "terminal.json"))
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(folder / "termination.json", status)
    return validate_terminal(directory, unit, frozen)


def seal(directory):
    directory = Path(directory).resolve()
    frozen, _, _ = read_control(directory)
    outcomes = {unit: validate_terminal(directory, unit, frozen) for unit in UNITS}
    selections = {
        condition: original.select(
            [
                outcome["selection"]
                for outcome in outcomes.values()
                if outcome["condition"] == condition and outcome["selection"] is not None
            ]
        )
        for condition in CONDITIONS
    }
    value = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        units={unit: binding(directory / "units" / unit / "terminal.json") for unit in UNITS},
        selections=selections,
        optimizer_calls=sum(o["optimizer_calls"] for o in outcomes.values()),
        inherited_low_fits=6,
        maximum_new_optimizer_calls=24,
        reference_usage="none",
        held_usage="none",
        half_view_scope=POLICY["half_view_scope"],
    )
    immutable(directory / "terminal.json", value)
    return read(directory / "terminal.json")


def evaluate(directory):
    """Join configured-reference errors only after all twelve units are sealed."""
    directory = Path(directory).resolve()
    terminal = seal(directory)
    frozen, parent, _ = read_control(directory)
    if (
        parent["original"]["member"]["role"] != "development"
        or parent["original"]["member"]["label"] != frozen["label"]
    ):
        raise ValueError("A control reference join is development-only")
    from ds21_evaluate import coordinates, distance_km, reference

    from leo.contracts.regional_position import RegionalPrior

    expected = reference()
    prior = RegionalPrior(**frozen["inputs"]["prior"])
    rows = []
    for condition in CONDITIONS:
        winner = terminal["selections"][condition]
        row = dict(condition=condition, view="final-all", arm="fitted-c", state="unavailable")
        if winner is not None:
            location = coordinates(prior, winner["fit"]["vector"][:2])
            error = distance_km(location, expected)
            row.update(
                state="estimated",
                start=winner["start"],
                proposal_id=original.PROPOSAL_IDS[winner["start"]],
                coordinates_deg=list(location),
                error_km=error,
                below_1km=error < 1,
                below_0_5km=error < 0.5,
                fitted_c_hz_per_ghz=winner["fit"]["vector"][6],
                training_objective=winner["fit"]["objective"],
                training_likelihood_nll=winner["fit"]["likelihood_nll"],
                training_frequency_rms_hz=winner["fit"].get("posterior_rms_hz"),
            )
        rows.append(row)
    value = dict(
        label=frozen["label"],
        parent_schema=frozen["parent_schema"],
        terminal=binding(directory / "terminal.json"),
        evaluator=binding(__file__),
        reference_source=binding(
            Path(__file__).resolve().parents[1] / "src/leo/cli/regional_position.py"
        ),
        rows=rows,
        reference_usage="Only after all twelve scientific units and selectors sealed",
        limitation=POLICY["half_view_scope"] + "; configured reference, not independently surveyed",
    )
    immutable(directory / "development-errors.json", value)
    return read(directory / "development-errors.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "seal", "evaluate"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--unit", choices=UNITS)
    args = parser.parse_args()
    if args.command == "freeze":
        if args.model_directory is None:
            parser.error("--model-directory required")
        result = freeze(args.directory, model_directory=args.model_directory)
    elif args.command == "run":
        if args.unit is None:
            parser.error("--unit required")
        result = run_unit(args.directory, args.unit)
    elif args.command == "seal":
        result = seal(args.directory)
    else:
        result = evaluate(args.directory)
    print(json.dumps(json_value(result)), flush=True)


if __name__ == "__main__":
    main()
