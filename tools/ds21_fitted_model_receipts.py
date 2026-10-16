"""Versioned metadata review of immutable original fitted-model receipts.

Recognize only the frozen sequential core's explicit high-stage descriptive
override. Every raw fit field remains exact. Existing numerical adapters, seeds,
fits, sources and receipts are never changed or retried by this compatibility
reader. New units delegate to the untouched v2 numerical adapter once.
"""

import argparse
import json
from pathlib import Path

import ds21_fitted_models_v2 as numerical
import numpy as np
from ds21_common import immutable

from leo.application.hard60_runner import HARD60_SCORE

original = numerical.original
binding, read = original.binding, original.read
POLICY = dict(
    schema="ds21-fitted-model-receipt-review-v1",
    scientific_schema=numerical.POLICY["schema"],
    high_offset_parameterization="uncentred-high-minus-low",
    high_training_fractions_override=None,
    reference_usage="none",
    held_usage="none",
    failed_retry=False,
)


def sources():
    return {**numerical.sources(), str(Path(__file__).resolve()): binding(__file__)["sha256"]}


def freeze(directory, *, model_directory):
    directory, model_directory = Path(directory).resolve(), Path(model_directory).resolve()
    frozen, _ = numerical.read_control(model_directory)
    original.initialization(model_directory, frozen)
    source = sources()
    value = dict(
        policy=POLICY,
        label=frozen["label"],
        model_directory=str(model_directory),
        model_protocol=binding(model_directory / "protocol.json"),
        initialization=binding(model_directory / "initialization.json"),
        source_sha256=source,
        snapshot_paths=original.discovery.archive_sources(directory, source),
    )
    immutable(directory / "protocol.json", value)
    return read_control(directory)[0]


def read_control(directory):
    directory = Path(directory).resolve()
    frozen = read(directory / "protocol.json")
    if frozen["policy"] != POLICY:
        raise ValueError("Model receipt review policy changed")
    original.pool.shape_parent.validate_archives(directory, frozen)
    if sources() != frozen["source_sha256"]:
        raise ValueError("Model receipt review source closure changed")
    model_directory = Path(frozen["model_directory"])
    model, _ = numerical.read_control(model_directory)
    if (
        model["label"] != frozen["label"]
        or binding(model_directory / "protocol.json") != frozen["model_protocol"]
        or binding(model_directory / "initialization.json") != frozen["initialization"]
    ):
        raise ValueError("Immutable numerical model/initialization binding changed")
    original.initialization(model_directory, model)
    return frozen, model_directory, model


def high_diagnostic(value, row, initial):
    if "training_high_fractions" not in row["fit"]:
        expected = dict(
            row["fit"],
            converged=row["stationary"],
            training_high_fractions=None,
            offset_parameterization=POLICY["high_offset_parameterization"],
        )
        if row["stationary"] or value != expected:
            raise ValueError("Failed high-stage descriptive override scope differs")
        return
    receivers = row["fit"]["group_receivers"]
    if receivers != initial["models"]["A"]["high"]["observation_receivers"] or row["fit"][
        "training_high_fractions"
    ] != [0.5] * len(receivers):
        raise ValueError("Known high-stage internal frame differs")
    additions = {"offset_parameterization"}
    if row["stationary"]:
        additions.add("offset_timing_diagnostic")
    if (
        set(value) != set(row["fit"]) | additions
        or value["training_high_fractions"] is not None
        or value["offset_parameterization"] != POLICY["high_offset_parameterization"]
    ):
        raise ValueError("High-stage descriptive override scope differs")
    expected = dict(row["fit"], converged=row["stationary"], training_high_fractions=None)
    if any(value.get(k) != v for k, v in expected.items()):
        raise ValueError("Sequential high scientific call field changed")
    if row["stationary"]:
        diagnostic = value["offset_timing_diagnostic"]
        if set(diagnostic) != {f"rx{r}" for r in receivers}:
            raise ValueError("Known high offset/timing diagnostic receiver coverage differs")
        windows, mass = 0, 0.0
        for item in diagnostic.values():
            if set(item) != {
                "windows",
                "signal_windows",
                "offset_information_hz_minus_2",
                "timing_explained_offset_fraction",
            }:
                raise ValueError("Known high offset/timing diagnostic fields differ")
            n, m, info, fraction = (
                item[k]
                for k in (
                    "windows",
                    "signal_windows",
                    "offset_information_hz_minus_2",
                    "timing_explained_offset_fraction",
                )
            )
            if (
                type(n) is not int
                or n <= 0
                or not np.isfinite([m, info]).all()
                or not 0 <= m <= n
                or info < 0
                or not np.isclose(info, m / HARD60_SCORE.sigma_hz**2, rtol=1e-12, atol=1e-12)
                or (info == 0 and fraction is not None)
                or (
                    info > 0
                    and (fraction is None or not np.isfinite(fraction) or not 0 <= fraction <= 1)
                )
            ):
                raise ValueError("Known high offset/timing diagnostic domain differs")
            windows, mass = windows + n, mass + m
        if windows != initial["models"]["A"]["high"]["windows"] or not np.isclose(
            mass, row["fit"]["signal_windows"], rtol=0, atol=1e-7
        ):
            raise ValueError("Known high offset/timing diagnostic window/mass coverage differs")


def validate_unit(model_directory, unit, frozen):
    """Resume only the metadata check after the literal known v1 rejection."""
    try:
        value = original.sealed_unit(model_directory, unit, frozen)
        if unit.startswith("A-") and "high" in value.get("calls", {}):
            high_diagnostic(
                value["path"]["high"],
                value["calls"]["high"],
                original.initialization(model_directory, frozen),
            )
        return value, {}
    except ValueError as error:
        if str(error) != "Sequential path/call diagnostic changed" or not unit.startswith("A-"):
            raise
    model_directory = Path(model_directory)
    sha = binding(model_directory / "protocol.json")["sha256"]
    initial = original.initialization(model_directory, frozen)
    rows = original.calls(model_directory, unit, sha)
    value = read(model_directory / "units" / unit / "terminal.json")
    for key, row in rows.items():
        if key == "high":
            high_diagnostic(value["path"][key], row, initial)
        elif value["path"][key] != dict(row["fit"], converged=row["stationary"]):
            raise ValueError("Sequential scientific stage/call field changed")
    # The unchanged validator already checked exact initialization, every call's
    # options/seed/center/layout and prerequisite status before its rejection.
    # Complete all subsequent coverage/selection/scalar checks here.
    status = value["path"]["status"]
    expected_calls = (
        {"low"}
        if status == "low-nonstationary"
        else {"low", "high"}
        if status == "high-nonstationary"
        else {"low", "high", "final"}
    )
    winner = rows.get("final") if status == "complete" else None
    if (
        value["protocol_sha256"] != sha
        or value["label"] != frozen["label"]
        or value["unit"] != unit
        or value["state"] != "complete"
        or value["calls"] != rows
        or set(rows) != expected_calls
        or value["optimizer_calls"] != len(rows)
        or value["skipped_calls"] != [k for k in ("low", "high", "final") if k not in rows]
        or value["selection"] != winner
        or (winner is not None and not winner["stationary"])
        or value["initialization"] != binding(model_directory / "initialization.json")
        or value["reference_usage"] != "none"
        or value["held_usage"] != "none"
        or not original.slices(model_directory / "units" / unit, sha, unit)
    ):
        raise ValueError("Reviewed unit coverage/selection seal differs")
    diagnostic = value["diagnostics"]
    if winner is None:
        if diagnostic is not None:
            raise ValueError("Unavailable reviewed selection has diagnostics")
    elif (
        set(diagnostic) != {"objective", "likelihood_nll"}
        or not np.isfinite([diagnostic["objective"], diagnostic["likelihood_nll"]]).all()
        or abs(diagnostic["objective"] - winner["fit"]["objective"]) > 1e-7
        or abs(diagnostic["likelihood_nll"] - winner["fit"]["likelihood_nll"]) > 1e-7
    ):
        raise ValueError("Reviewed selected scientific scalar diagnostic differs")
    return value, {
        "high.training_high_fractions": dict(
            call=rows["high"]["fit"]["training_high_fractions"],
            path=None,
            offset_parameterization=POLICY["high_offset_parameterization"],
            reason=(
                "Explicit descriptive override in frozen original sequential core; "
                "all raw fit fields preserved"
            ),
        )
    }


def review_unit(directory, unit):
    original.unit_spec(unit)
    directory = Path(directory).resolve()
    frozen, model_directory, model = read_control(directory)
    outcome, overrides = validate_unit(model_directory, unit, model)
    inventory = original.failure_inventory(model_directory, unit)
    terminal = (
        model_directory
        / "units"
        / unit
        / ("terminal.json" if outcome["state"] == "complete" else "finalized-failure.json")
    )
    value = dict(
        review_protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        unit=unit,
        scientific_outcome=outcome,
        scientific_terminal=binding(terminal),
        scientific_inventory=inventory,
        metadata_overrides=overrides,
        review_location_optimizer_calls=0,
        scientific_optimizer_calls=outcome.get(
            "optimizer_calls", sum(1 for p in outcome.get("inventory", {}) if "/launches/" in p)
        ),
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "units" / f"{unit}.json", value)
    return read(directory / "units" / f"{unit}.json")


def run_unit(directory, unit, *, slice_id, maximum_seconds=None):
    original.unit_spec(unit)
    frozen, model_directory, _ = read_control(directory)
    folder = model_directory / "units" / unit
    if (folder / "terminal.json").exists() or (folder / "finalized-failure.json").exists():
        return review_unit(directory, unit)
    try:
        result = numerical.run_slice(
            model_directory, unit, slice_id=slice_id, maximum_seconds=maximum_seconds
        )
    except ValueError as error:
        if str(error) != "Sequential path/call diagnostic changed":
            raise
        return review_unit(directory, unit)
    if result.get("state") == "checkpointed":
        return result
    return review_unit(directory, unit)


def seal(directory):
    directory = Path(directory).resolve()
    frozen, _, _ = read_control(directory)
    reviews = {u: review_unit(directory, u) for u in original.UNITS}
    outcomes = {u: r["scientific_outcome"] for u, r in reviews.items()}
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
        review_protocol_sha256=binding(directory / "protocol.json")["sha256"],
        reviews={u: binding(directory / "units" / f"{u}.json") for u in reviews},
        outcomes=outcomes,
        selections=selections,
        optimizer_calls=sum(
            o.get("optimizer_calls", sum(1 for p in o.get("inventory", {}) if "/launches/" in p))
            for o in outcomes.values()
        ),
        maximum_optimizer_calls=54,
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "terminal.json", value)
    return read(directory / "terminal.json")


def evaluate(directory):
    directory = Path(directory).resolve()
    terminal = seal(directory)
    _, _, model = read_control(directory)
    from ds21_evaluate import coordinates, distance_km, reference

    from leo.contracts.regional_position import RegionalPrior

    expected, rows, prior = reference(), [], RegionalPrior(**model["inputs"]["prior"])
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
    value = dict(
        label=terminal["label"],
        arm="fitted-c",
        rows=rows,
        terminal=binding(directory / "terminal.json"),
        evaluator=binding(__file__),
        reference_usage="After all twelve scientific outcomes and metadata reviews sealed",
        limitation=numerical.POLICY["A_scope"]
        + "; "
        + numerical.POLICY["half_view_limitation"]
        + "; "
        + numerical.POLICY["C_limitation"],
        calibration_initialization=numerical.POLICY["calibration_initialization"],
    )
    immutable(directory / "development-errors.json", value)
    return read(directory / "development-errors.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("freeze", "review-unit", "run-unit", "seal", "evaluate")
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--unit", choices=original.UNITS)
    parser.add_argument("--slice-id", type=int)
    parser.add_argument("--maximum-seconds", type=float)
    args = parser.parse_args()
    if args.command == "freeze":
        if args.model_directory is None:
            parser.error("--model-directory required")
        result = freeze(args.directory, model_directory=args.model_directory)
    elif args.command in ("review-unit", "run-unit"):
        if args.unit is None or (args.command == "run-unit" and args.slice_id is None):
            parser.error("--unit and explicitrun --slice-id required")
        result = (
            review_unit(args.directory, args.unit)
            if args.command == "review-unit"
            else run_unit(
                args.directory,
                args.unit,
                slice_id=args.slice_id,
                maximum_seconds=args.maximum_seconds,
            )
        )
    else:
        result = seal(args.directory) if args.command == "seal" else evaluate(args.directory)
    print(
        json.dumps(
            dict(
                label=result.get("label"),
                command=args.command,
                state=result.get("state", "reviewed"),
                recorded_optimizer_calls=result.get(
                    "scientific_optimizer_calls", result.get("optimizer_calls", 0)
                ),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
