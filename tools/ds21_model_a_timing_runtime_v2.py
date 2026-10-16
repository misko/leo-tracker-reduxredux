"""Checkpoint-preserving A timing control with one qualified authority freeze.

Scientific models and 20-second call budgets are unchanged. An exact flat byte
manifest replaces repeated recursive parent reconstruction during bounded units.
The four failed v1 outer attempts remain immutable; their eight saved fits can
be recovered as metadata only, without objective, predictor or optimizer calls.
"""

import argparse
import json
import time
from contextlib import suppress
from pathlib import Path

import ds21_model_a_timing_locked_control as previous
import model_a_verified_manifest as manifest
import numpy as np

original = previous.original
binding, read = original.binding, original.read
CONDITIONS, UNITS = previous.CONDITIONS, previous.UNITS
POLICY = dict(
    previous.POLICY,
    schema="ds21-model-a-timing-runtime-v2",
    source_qualification="Genuine v1 qualified parent reader once; flat exact-byte checks per unit",
    maximum_new_optimizer_calls=20,
    inherited_v1_calls=4,
    maximum_total_optimizer_calls=24,
    preparation_seconds=30,
    validation_reserve_seconds=5,
    metadata_recovery="Own start-0 complete stationary call triples from failed v1 outer unit",
)


def native_json(value):
    """Normalize tuples and NumPy scalars without changing numerical values."""
    if isinstance(value, np.ndarray):
        return native_json(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: native_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [native_json(v) for v in value]
    return value


def immutable(path, value):
    previous.immutable(Path(path), native_json(value))


def sources():
    return {
        **previous.sources(),
        str(Path(__file__).resolve()): binding(__file__)["sha256"],
        str(Path(manifest.__file__).resolve()): binding(manifest.__file__)["sha256"],
    }


def freeze(directory, *, failed_directory):
    directory, failed_directory = Path(directory).resolve(), Path(failed_directory).resolve()
    if (directory / "protocol.json").exists():
        frozen = read_control(directory)
        if frozen["failed_directory"] != str(failed_directory):
            raise ValueError("Existing v2 failed-parent directory differs")
        return frozen
    # This is the genuine expensive recursive qualification, never a schema relabel.
    old, parent, _ = previous.read_control(failed_directory)
    if old["parent_schema"] != previous.coverage.POLICY["schema"]:
        raise ValueError("This measured v2 requires qualified coverage parents")
    coverage_directory = Path(parent["stages"]["coverage-discovery"])
    coverage_frozen = read(coverage_directory / "protocol.json")
    bank_directory = Path(coverage_frozen["full_bank"]["path"]).parent
    case_directory = Path(parent["case_directory"])
    directories = {
        failed_directory,
        Path(old["model_directory"]),
        case_directory,
        bank_directory,
        *(Path(p) for p in parent["stages"].values()),
    }
    files = set()
    case_source = read(case_directory / "source-protocol.json")
    for key in ("membership", "census", "input"):
        files.add(Path(case_source[key]["path"]))
    files.add(Path(coverage_frozen["snapshot"]["path"]))
    source = sources()
    files.update(Path(p) for p in source)
    value = dict(
        policy=POLICY,
        label=old["label"],
        failed_directory=str(failed_directory),
        failed_protocol=binding(failed_directory / "protocol.json"),
        qualified_parent_protocol=old["model_protocol"],
        original=old,
        case_protocol=binding(case_directory / "protocol.json"),
        case_source_protocol=binding(case_directory / "source-protocol.json"),
        bank_directory=str(bank_directory),
        bank_protocol=binding(bank_directory / "protocol.json"),
        source_sha256=source,
        snapshot_paths=original.discovery.archive_sources(directory, source),
        authority_files=manifest.pin_qualified_files(
            directories,
            source_files=source,
            extra_files=files,
        ),
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "protocol.json", value)
    return read_control(directory)


def read_control(directory):
    directory = Path(directory).resolve()
    frozen = read(directory / "protocol.json")
    if (
        frozen["policy"] != POLICY
        or frozen["reference_usage"] != "none"
        or frozen["held_usage"] != "none"
    ):
        raise ValueError("A runtime-v2 policy changed")
    original.pool.shape_parent.validate_archives(directory, frozen)
    # No repeated AST traversal is needed: the exact qualified live bytes and
    # every ancestor archive/receipt/input/bank byte are independently hashed.
    expected = dict(frozen["authority_files"])
    expected["files"] = {**expected["files"], **frozen["source_sha256"]}
    manifest.verify_pinned_files(expected)
    return frozen


def prepare_case(frozen):
    """Replay the original preparation and bank-loading ports from pinned bytes."""
    source = original.read_bound(frozen["case_source_protocol"])
    member = source["member"]
    if member["label"] != frozen["label"] or member["role"] != "development":
        raise ValueError("A runtime-v2 requires its own development member")
    case = original.discovery.prepare_training_case(
        member,
        original.read_bound(source["membership"]),
        original.read_bound(source["census"]),
    )
    original.discovery.validate_preparation(case, original.read_bound(frozen["case_protocol"]))
    full, _ = original.discovery.load_bank(
        Path(frozen["bank_directory"]), frozen["bank_protocol"]["sha256"]
    )
    case["bank"] = full.select(frozen["original"]["inputs"]["candidate_full_indices"])
    if (
        case["bank"].numbers.tolist() != frozen["original"]["inputs"]["candidate_numbers"]
        or {v: p.evidence_sha256 for v, p in case["prepared"].items()}
        != frozen["original"]["inputs"]["prepared"]
    ):
        raise ValueError("A runtime-v2 training rows/bank differ from qualified parent")
    return case


def qualify(directory, output):
    """Measure byte checks and exact training replay with zero fits or predictions."""
    stages, start = {}, time.monotonic()
    frozen = read_control(directory)
    stages["authority_check_seconds"] = time.monotonic() - start
    start = time.monotonic()
    with original.discovery.slice_bound(POLICY["preparation_seconds"]):
        case = prepare_case(frozen)
    stages["preparation_seconds"] = time.monotonic() - start
    start = time.monotonic()
    read_control(directory)
    stages["post_authority_check_seconds"] = time.monotonic() - start
    value = dict(
        schema="ds21-model-a-runtime-v2-zero-fit-qualification",
        label=frozen["label"],
        protocol=binding(Path(directory) / "protocol.json"),
        stage_seconds=stages,
        authority_files=len(frozen["authority_files"]["files"]),
        optimizer_calls=0,
        predictor_calls=0,
        objective_calls=0,
        reference_usage="none",
        held_usage="none",
        training_windows={
            v: len(case["prepared"][v].observations.window_ids) for v in original.VIEWS
        },
    )
    immutable(output, value)
    return value


def validate_call(row, *, identity, condition, index, stage, low, frozen):
    expected_options = dict(arm="fitted-c", seconds=20, iterations=600)
    if stage == "high":
        expected_options["fixed_position"] = True
        if condition == CONDITIONS[1]:
            expected_options.update(fixed_timing=True, timing_source="own-low")
    else:
        expected_options.update(local_center=low["local_center"], local_radius_km=25)
    if (
        any(row.get(k) != v for k, v in dict(**identity, call=stage).items())
        or row["condition"] != condition
        or row["start"] != index
        or row["options"] != expected_options
        or row["local_center"] != low["local_center"]
        or row["stationary"]
        != original.transfer.stationary(
            row["fit"], row["local_center"], row["parameter_count"], row["nuisance_count"]
        )
    ):
        raise ValueError("A runtime-v2 call identity/options/stationarity differ")
    if stage == "high":
        initial = original.read_bound(frozen["original"]["initialization"])
        timing = (
            low["fit"]["vector"][7:]
            if condition == CONDITIONS[1]
            else initial["starts"]["A"]["high"][index]["seed"]["vector"][7:]
        )
        if (
            row["seed"]["vector"][:2] != low["fit"]["vector"][:2]
            or row["seed"]["vector"][2:7] != [0] * 5
            or row["seed"]["vector"][7:] != timing
        ):
            raise ValueError("A runtime-v2 high own-low/high-donor physical seed differs")
        if (
            condition == CONDITIONS[1]
            and "vector" in row["fit"]
            and (
                row["fit"].get("fixed_timing") is not True
                or row["fit"].get("stationarity_scope")
                != "receiver-offsets-only; low-position-correction-timing-fixed"
                or row["fit"]["vector"] != row["seed"]["vector"]
            )
        ):
            raise ValueError("A runtime-v2 high timing certificate differs")


def receipt_path(low, rows):
    """A scientific outcome from complete saved rows; no fabricated diagnostics."""
    expected = (
        set()
        if not low["stationary"]
        else {"high", "final"}
        if rows.get("high", {}).get("stationary")
        else {"high"}
    )
    if set(rows) != expected:
        raise ValueError("A runtime-v2 prerequisite call inventory differs")
    status = (
        "low-nonstationary"
        if not low["stationary"]
        else "high-nonstationary"
        if not rows["high"]["stationary"]
        else "final-nonstationary"
        if not rows["final"]["stationary"]
        else "complete"
    )
    result = dict(status=status, low=dict(low["fit"], converged=low["stationary"]))
    result.update({key: dict(row["fit"], converged=row["stationary"]) for key, row in rows.items()})
    if "high" in rows:
        result.update(
            fixed_shift_receivers=rows["high"]["fit"].get("group_receivers", []),
            fixed_shift_hz=rows["high"]["fit"].get("group_offsets_hz", []),
        )
    return result


def recover(directory, unit):
    directory = Path(directory).resolve()
    condition, index = previous.unit_spec(unit)
    if index != 0:
        raise ValueError("Only the four declared v1 start-0 attempts may be recovered")
    frozen = read_control(directory)
    old = Path(frozen["failed_directory"])
    folder = old / "units" / unit
    identity = dict(protocol_sha256=frozen["failed_protocol"]["sha256"], unit=unit)
    status = read(folder / "termination.json")
    if (
        read(folder / "launch.json") != identity
        or any(status.get(k) != v for k, v in identity.items())
        or status["state"] != "failed"
        or status.get("error_type") not in {"TypeError", "SliceHardStop"}
        or (folder / "terminal.json").exists()
    ):
        raise ValueError("A runtime-v2 recovery requires the declared failed outer attempt")
    low = original.read_bound(frozen["original"]["inherited_low"][str(index)])
    if not low["stationary"]:
        raise ValueError("A runtime-v2 recovery requires its own stationary low fit")
    rows, receipts = {}, {}
    for kind in ("calls", "launches", "terminations"):
        if {p.stem for p in (folder / kind).glob("*.json")} != {"high", "final"}:
            raise ValueError("A runtime-v2 recovery requires exactly two complete call triples")
    for stage in ("high", "final"):
        path = folder / "calls" / f"{stage}.json"
        row = read(path)
        claim = dict(**identity, call=stage)
        if read(folder / "launches" / path.name) != claim or read(
            folder / "terminations" / path.name
        ) != dict(**claim, call_receipt=binding(path)):
            raise ValueError("A runtime-v2 recovery scientific call authority differs")
        validate_call(
            row,
            identity=identity,
            condition=condition,
            index=index,
            stage=stage,
            low=low,
            frozen=frozen,
        )
        if not row["stationary"]:
            raise ValueError("A runtime-v2 recovery only accepts complete stationary saved stages")
        rows[stage], receipts[stage] = row, binding(path)
    if (
        rows["final"]["seed"]["vector"][:2] != low["fit"]["vector"][:2]
        or rows["final"]["seed"]["vector"][7:] != rows["high"]["fit"]["vector"][7:]
    ):
        raise ValueError("A runtime-v2 recovery dependent final physical seed differs")
    value = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        unit=unit,
        condition=condition,
        start=index,
        state="recovered-metadata-only",
        retained_outer_failure=binding(folder / "termination.json"),
        original_call_receipts=receipts,
        inherited_low=frozen["original"]["inherited_low"][str(index)],
        calls=rows,
        path=receipt_path(low, rows),
        selection=rows["final"],
        optimizer_calls=0,
        reused_v1_optimizer_calls=2,
        recovery_objective_calls=0,
        recovery_predictor_calls=0,
        unavailable_in_memory_diagnostics=["calibration_projection", "offset_timing_diagnostic"],
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "units" / unit / "terminal.json", value)
    return value


def run(directory, unit):
    directory = Path(directory).resolve()
    condition, index = previous.unit_spec(unit)
    if index == 0:
        return recover(directory, unit)
    begun = time.monotonic()
    frozen = read_control(directory)
    initial = original.read_bound(frozen["original"]["initialization"])
    low = original.read_bound(frozen["original"]["inherited_low"][str(index)])
    folder = directory / "units" / unit
    if (folder / "terminal.json").exists():
        return validate_unit(directory, unit, frozen)
    if (folder / "launch.json").exists() or (folder / "termination.json").exists():
        raise ValueError("A runtime-v2 orphan/failed unit; no retry")
    identity = dict(protocol_sha256=binding(directory / "protocol.json")["sha256"], unit=unit)
    immutable(folder / "launch.json", identity)
    status, rows = dict(**identity, state="failed"), {}
    try:
        with original.discovery.slice_bound(max(0.001, 90 - (time.monotonic() - begun))):
            with original.discovery.slice_bound(POLICY["preparation_seconds"]):
                case = prepare_case(frozen)
            # The nested preparation timer clears SIGALRM; restore the remaining
            # whole-unit deadline explicitly around all scientific work/checks.
            with original.discovery.slice_bound(max(0.001, 90 - (time.monotonic() - begun))):
                starts = {v: initial["starts"]["A"][v][index] for v in original.VIEWS}
                models = {
                    v: original.objective(
                        case["prepared"][v], case["bank"], case["prior"], case["nodes"]
                    )
                    for v in original.VIEWS
                }
                high_base = original.objective(
                    case["prepared"]["high"],
                    case["bank"],
                    case["prior"],
                    case["nodes"],
                    common_clock=False,
                ).base

                def stage_fit(stage, model, vector, nuisance, options):
                    if stage == "low":
                        if (
                            native_json(vector) != low["seed"]["vector"]
                            or native_json(nuisance) != low["seed"]["nuisance"]
                            or native_json(options) != low["options"]
                        ):
                            raise ValueError("A runtime-v2 own low seed/options differ")
                        return dict(low["fit"], converged=low["stationary"])
                    if time.monotonic() - begun + 20 + POLICY["validation_reserve_seconds"] >= 90:
                        raise TimeoutError("Insufficient remaining unit budget; no retry")
                    vector = np.asarray(vector, float).copy()
                    locked = stage == "high" and condition == CONDITIONS[1]
                    if locked:
                        vector[7:] = low["fit"]["vector"][7:]
                    path = folder / "calls" / f"{stage}.json"
                    claim = dict(**identity, call=stage)
                    immutable(folder / "launches" / path.name, claim)
                    try:
                        fit = (
                            previous.experiment.fit_timing_locked_high(model, vector, nuisance)
                            if locked
                            else original.fit_group_calibration(model, vector, nuisance, **options)
                        )
                    except (ValueError, TimeoutError) as error:
                        fit = dict(
                            converged=False, error_type=type(error).__name__, reason=str(error)
                        )
                    stationary = original.transfer.stationary(
                        fit, low["local_center"], model.size, len(model.initial_nuisance)
                    )
                    row = dict(
                        **claim,
                        condition=condition,
                        start=index,
                        options=dict(options, fixed_timing=True, timing_source="own-low")
                        if locked
                        else options,
                        seed=dict(vector=vector, nuisance=nuisance),
                        local_center=low["local_center"],
                        parameter_count=model.size,
                        nuisance_count=len(model.initial_nuisance),
                        fit=fit,
                        stationary=stationary,
                    )
                    immutable(path, row)
                    immutable(
                        folder / "terminations" / path.name,
                        dict(**claim, call_receipt=binding(path)),
                    )
                    rows[stage] = read(path)
                    if stage == "final" and not stationary:
                        raise original.FinalStageUnavailable()
                    return dict(rows[stage]["fit"], converged=stationary)

                with suppress(original.FinalStageUnavailable):
                    original.fit_sequential_path(
                        models["low"],
                        high_base,
                        models["all"].base,
                        *(np.asarray(starts[v]["seed"]["vector"]) for v in ("low", "high", "all")),
                        low_nuisance=np.asarray(starts["low"]["seed"]["nuisance"]),
                        high_correction_seed=original.decode_physical_correction(
                            starts["high"]["proposal"]
                        ),
                        local_center=low["local_center"],
                        local_radius_km=25,
                        stage_fit=stage_fit,
                        arm="fitted-c",
                        seconds=20,
                        iterations=600,
                    )
                outcome = receipt_path(low, rows)
                read_control(directory)
                value = dict(
                    **identity,
                    label=frozen["label"],
                    condition=condition,
                    start=index,
                    state="complete",
                    inherited_low=frozen["original"]["inherited_low"][str(index)],
                    calls=rows,
                    path=outcome,
                    optimizer_calls=len(rows),
                    reused_v1_optimizer_calls=0,
                    selection=rows.get("final") if outcome["status"] == "complete" else None,
                    reference_usage="none",
                    held_usage="none",
                )
                immutable(folder / "terminal.json", value)
                status = dict(
                    **identity,
                    state="complete",
                    terminal=binding(folder / "terminal.json"),
                    elapsed_seconds=time.monotonic() - begun,
                )
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(folder / "termination.json", status)
    return validate_unit(directory, unit, frozen)


def validate_unit(directory, unit, frozen):
    condition, index = previous.unit_spec(unit)
    folder = Path(directory) / "units" / unit
    value = read(folder / "terminal.json")
    if value["state"] == "recovered-metadata-only":
        # Rebuild the exact receipt-only recovered outcome, idempotently checking
        # all retained v1 claims/hashes; this executes no scientific calculations.
        expected = recover(directory, unit)
        if value != native_json(expected):
            raise ValueError("A runtime-v2 recovered metadata changed")
        return value
    identity = dict(protocol_sha256=binding(Path(directory) / "protocol.json")["sha256"], unit=unit)
    status = read(folder / "termination.json")
    if (
        read(folder / "launch.json") != identity
        or status["state"] != "complete"
        or any(status.get(k) != v for k, v in identity.items())
        or status["terminal"] != binding(folder / "terminal.json")
    ):
        raise ValueError("A runtime-v2 outer launch/termination changed")
    low = original.read_bound(value["inherited_low"])
    if (
        value["state"] != "complete"
        or value["inherited_low"] != frozen["original"]["inherited_low"][str(index)]
        or value["unit"] != unit
        or value["label"] != frozen["label"]
    ):
        raise ValueError("A runtime-v2 own low/unit identity differs")
    rows = value["calls"]
    for kind in ("calls", "launches", "terminations"):
        if {p.stem for p in (folder / kind).glob("*.json")} != set(rows):
            raise ValueError("A runtime-v2 missing/extra call inventory")
    for stage, row in rows.items():
        path = folder / "calls" / f"{stage}.json"
        claim = dict(**identity, call=stage)
        if (
            row != read(path)
            or read(folder / "launches" / path.name) != claim
            or read(folder / "terminations" / path.name)
            != dict(**claim, call_receipt=binding(path))
        ):
            raise ValueError("A runtime-v2 call authority changed")
        validate_call(
            row,
            identity=identity,
            condition=condition,
            index=index,
            stage=stage,
            low=low,
            frozen=frozen,
        )
    outcome = receipt_path(low, rows)
    winner = rows.get("final") if outcome["status"] == "complete" else None
    if (
        value["path"] != native_json(outcome)
        or value["selection"] != winner
        or value["optimizer_calls"] != len(rows)
        or value["reused_v1_optimizer_calls"] != 0
        or value["protocol_sha256"] != identity["protocol_sha256"]
        or value["condition"] != condition
        or value["start"] != index
        or value["reference_usage"] != "none"
        or value["held_usage"] != "none"
    ):
        raise ValueError("A runtime-v2 scientific path/selection differs")
    return value


def seal(directory):
    directory = Path(directory).resolve()
    frozen = read_control(directory)
    outcomes = {u: validate_unit(directory, u, frozen) for u in UNITS}
    value = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        units={u: binding(directory / "units" / u / "terminal.json") for u in UNITS},
        selections={
            c: original.select(
                [
                    o["selection"]
                    for o in outcomes.values()
                    if o["condition"] == c and o["selection"] is not None
                ]
            )
            for c in CONDITIONS
        },
        new_optimizer_calls=sum(o["optimizer_calls"] for o in outcomes.values()),
        reused_v1_optimizer_calls=sum(o["reused_v1_optimizer_calls"] for o in outcomes.values()),
        inherited_low_fits=6,
        reference_usage="none",
        held_usage="none",
    )
    if value["new_optimizer_calls"] > 20 or value["reused_v1_optimizer_calls"] != 4:
        raise ValueError("A runtime-v2 prescribed call budget/recovery differs")
    immutable(directory / "terminal.json", value)
    return value


def evaluate(directory):
    directory = Path(directory).resolve()
    terminal, frozen = seal(directory), read_control(directory)
    from ds21_evaluate import coordinates, distance_km, reference

    from leo.contracts.regional_position import RegionalPrior

    expected, rows = reference(), []
    prior = RegionalPrior(**frozen["original"]["inputs"]["prior"])
    for condition, winner in terminal["selections"].items():
        row = dict(condition=condition, view="final-all", state="unavailable", arm="fitted-c")
        if winner is not None:
            location = coordinates(prior, winner["fit"]["vector"][:2])
            error = distance_km(location, expected)
            row.update(
                state="estimated",
                start=winner["start"],
                coordinates_deg=list(location),
                error_km=error,
                below_0_5km=error < 0.5,
                fitted_c_hz_per_ghz=winner["fit"]["vector"][6],
                objective=winner["fit"]["objective"],
                likelihood_nll=winner["fit"]["likelihood_nll"],
                frequency_rms_hz=winner["fit"].get("posterior_rms_hz"),
            )
        rows.append(row)
    value = dict(
        label=frozen["label"],
        terminal=binding(directory / "terminal.json"),
        rows=rows,
        reference_usage="After all twelve v2 outcomes sealed; never selection",
        limitation=POLICY["half_view_scope"] + "; configured reference, not independently surveyed",
    )
    immutable(directory / "development-errors.json", value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("freeze", "qualify", "recover", "run", "seal", "evaluate")
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--failed-directory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--unit", choices=UNITS)
    args = parser.parse_args()
    if args.command == "freeze":
        if args.failed_directory is None:
            parser.error("--failed-directory required")
        value = freeze(args.directory, failed_directory=args.failed_directory)
    elif args.command == "qualify":
        if args.output is None:
            parser.error("--output required")
        value = qualify(args.directory, args.output)
    elif args.command in {"recover", "run"}:
        if args.unit is None:
            parser.error("--unit required")
        value = (
            recover(args.directory, args.unit)
            if args.command == "recover"
            else run(args.directory, args.unit)
        )
    else:
        value = seal(args.directory) if args.command == "seal" else evaluate(args.directory)
    print(json.dumps(native_json(value), allow_nan=False))


if __name__ == "__main__":
    main()
