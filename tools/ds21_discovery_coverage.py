"""Prespecified training-only discovery grid control; original numerical ports."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import ds21_fitted_initialization as original
import numpy as np
from ds21_common import immutable, json_value

discovery = original.discovery
binding, read = original.binding, original.read
POLICY = dict(
    schema="ds21-discovery-coverage-control-v1",
    arm="fitted-c",
    points=100,
    levels_km=[50.0, 25.0, 12.5],
    priority_view="all",
    bootstrap_seconds=5,
    fixed_position_fit_seconds=5,
    fixed_position_fit_iterations=200,
    initial_centers=80,
    internal_seconds=480,
    external_term_seconds=495,
    external_kill_seconds=500,
    point_admission_reserve_seconds=31,
    failed_retry=False,
    held_usage="none",
    reference_usage="none",
    scope="Discovery-only grid sensitivity; no downstream six-proposal or A/B/C result",
)
CASE_FIELDS = (
    "start_utc_ns",
    "prepared",
    "prior",
    "partition",
    "training_frames",
    "clock_nodes_s",
    "snapshot",
)


def sources():
    evaluator = Path(__file__).with_name("ds21_evaluate.py")
    return {
        **original.sources(),
        str(Path(__file__).resolve()): binding(__file__)["sha256"],
        str(evaluator.resolve()): binding(evaluator)["sha256"],
    }


def freeze(directory, *, parent_discovery):
    directory, parent_discovery = Path(directory).resolve(), Path(parent_discovery).resolve()
    if (directory / "protocol.json").exists():
        frozen = read_control(directory)[0]
        if frozen["parent_discovery"] != str(parent_discovery):
            raise ValueError("Existing coverage parent discovery changed")
        return frozen
    parent = original.read_stage(parent_discovery, "discovery")
    case = parent["original"]["frozen"]
    if case["prior"]["radius_km"] != 250:
        raise ValueError("Prespecified 250 km prior required for the 80-center grid")
    source = sources()
    value = dict(
        policy=POLICY,
        label=parent["original"]["member"]["label"],
        parent_discovery=str(parent_discovery),
        parent_authority=parent["authority"],
        case_directory=str(parent["case_directory"]),
        case_protocol=binding(parent["case_directory"] / "protocol.json"),
        source_protocol=binding(parent["case_directory"] / "source-protocol.json"),
        full_bank=binding(parent_discovery / "bank.npz"),
        full_bank_receipt=binding(parent_discovery / "bank.json"),
        full_bank_count=len(parent["original"]["full_bank"].numbers),
        **{k: case[k] for k in CASE_FIELDS},
        source_sha256=source,
        snapshot_paths=discovery.archive_sources(directory, source),
    )
    immutable(directory / "protocol.json", value)
    return read_control(directory)[0]


def read_control(directory):
    directory = Path(directory).resolve()
    frozen = read(directory / "protocol.json")
    if frozen["policy"] != POLICY or sources() != frozen["source_sha256"]:
        raise ValueError("Coverage policy/scientific source closure changed")
    original.shape_parent.validate_archives(directory, frozen)
    parent_directory = Path(frozen["parent_discovery"])
    parent = original.read_stage(parent_directory, "discovery")
    case = parent["original"]["frozen"]
    if (
        parent["authority"] != frozen["parent_authority"]
        or str(parent["case_directory"]) != frozen["case_directory"]
        or binding(parent["case_directory"] / "protocol.json") != frozen["case_protocol"]
        or binding(parent["case_directory"] / "source-protocol.json") != frozen["source_protocol"]
        or binding(parent_directory / "bank.npz") != frozen["full_bank"]
        or binding(parent_directory / "bank.json") != frozen["full_bank_receipt"]
        or len(parent["original"]["full_bank"].numbers) != frozen["full_bank_count"]
        or parent["original"]["member"]["label"] != frozen["label"]
        or any(frozen[k] != case[k] for k in CASE_FIELDS)
        or frozen["prior"]["radius_km"] != 250
    ):
        raise ValueError("Original discovery/case/full-bank authority changed")
    return frozen, parent


def point_port(directory, frozen, parent, deadline):
    return discovery.AuditedPoints(
        directory,
        binding(directory / "protocol.json")["sha256"],
        parent["original"]["full_bank"],
        frozen,
        deadline,
    )


def validate_result(result, rows, radius):
    """Receipt-only hierarchy and unchanged original three-proposal selector."""
    result = json.loads(json.dumps(json_value(result), allow_nan=False))

    def score(east, north):
        key = f"point:{east:g}:{north:g}"
        if key not in rows:
            raise ValueError("Coverage hierarchy lacks a completed point")
        return rows[key]["selection_score"]

    replay = discovery.hierarchical_search(
        score,
        radius_km=radius,
        levels_km=POLICY["levels_km"],
        budget_points=100,
        edge_priority="nearest",
    )
    if json.loads(json.dumps(json_value(asdict(replay)), allow_nan=False)) != result["search"]:
        raise ValueError("Coverage terminal hierarchy changed")
    ranked = []
    for view in ("low", "high", "all"):
        eligible = [r for r in rows.values() if r["fits"].get(view, {}).get("converged")]
        if eligible:
            ranked.append(
                min(
                    eligible,
                    key=lambda r: (
                        r["fits"][view]["objective"],
                        r["east_km"],
                        r["north_km"],
                    ),
                )
            )
    ranked.extend(
        sorted(
            (r for r in rows.values() if r["selection_score"] < 1e100),
            key=lambda r: (r["selection_score"], r["east_km"], r["north_km"]),
        )
    )
    selected = []
    for row in ranked:
        if all(
            np.hypot(row["east_km"] - r["east_km"], row["north_km"] - r["north_km"]) >= 12.5
            for r in selected
        ):
            selected.append(row)
        if len(selected) == 3:
            break
    if (
        result["selected"] != selected
        or result["points"] != len(rows)
        or result["priority_view"] != "all"
        or result["available"] != (len(selected) == 3)
    ):
        raise ValueError("Coverage original training selector changed")


def read_terminal(directory):
    directory = Path(directory).resolve()
    frozen, parent = read_control(directory)
    sha = binding(directory / "protocol.json")["sha256"]
    if not original.check_slices(directory, sha):
        raise ValueError("Completed coverage slice required before terminal reuse")
    port = point_port(directory, frozen, parent, time.monotonic())
    rows, terminal = port.completed(), read(directory / "terminal.json")
    if (
        terminal["state"] != "complete"
        or terminal["label"] != frozen["label"]
        or terminal["protocol"] != binding(directory / "protocol.json")
        or terminal["full_bank"] != frozen["full_bank"]
        or terminal["points"] != {k: binding(port.path(k)) for k in rows}
        or terminal["reference_usage"] != "none"
        or terminal["held_usage"] != "none"
    ):
        raise ValueError("Coverage terminal source/point seal changed")
    validate_result(terminal["result"], rows, frozen["prior"]["radius_km"])
    return terminal


def run(directory, *, slice_id, maximum_seconds=480):
    directory = Path(directory).resolve()
    if (
        type(slice_id) is not int
        or slice_id < 0
        or not np.isfinite(maximum_seconds)
        or not 0 < maximum_seconds <= 480
    ):
        raise ValueError("Explicit nonnegative slice and <=480 seconds required")
    begun = time.monotonic()
    frozen, parent = read_control(directory)
    sha = binding(directory / "protocol.json")["sha256"]
    original.check_slices(directory, sha)
    port = point_port(directory, frozen, parent, begun + maximum_seconds)
    port.completed()
    if (directory / "terminal.json").exists():
        return read_terminal(directory)
    folder = directory / "slices"
    folder.mkdir(parents=True, exist_ok=True)
    identity = dict(protocol_sha256=sha, slice_id=slice_id)
    with (folder / f"{slice_id:03d}-launch.json").open("x") as stream:
        json.dump(identity, stream)
    status = dict(identity, state="failed")
    try:
        with discovery.slice_bound(max(0.001, maximum_seconds - (time.monotonic() - begun))):
            source = parent["original"]
            case = discovery.prepare_training_case(
                source["member"], source["membership"], source["census"]
            )
            discovery.validate_preparation(case, frozen)
            remaining = maximum_seconds - (time.monotonic() - begun)
            if remaining <= POLICY["point_admission_reserve_seconds"]:
                raise discovery.DiscoverySliceExpired("before-next-point")
            result = discovery.discover_channel_groups(
                case["prepared"],
                source["full_bank"],
                case["prior"],
                port,
                maximum_seconds=remaining,
                points=100,
                clock_nodes=case["nodes"],
                levels_km=POLICY["levels_km"],
                priority_view="all",
            )
            rows = port.completed()
            validate_result(result, rows, frozen["prior"]["radius_km"])
            read_control(directory)
            immutable(
                directory / "terminal.json",
                dict(
                    state="complete",
                    label=frozen["label"],
                    protocol=binding(directory / "protocol.json"),
                    full_bank=frozen["full_bank"],
                    points={k: binding(port.path(k)) for k in rows},
                    result=result,
                    elapsed_s=time.monotonic() - begun,
                    reference_usage="none",
                    held_usage="none",
                ),
            )
            status["state"] = "complete"
    except discovery.DiscoverySliceExpired as error:
        status.update(state="checkpointed", reason=str(error))
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        status["elapsed_s"] = time.monotonic() - begun
        immutable(folder / f"{slice_id:03d}-termination.json", status)
    return read_terminal(directory) if status["state"] == "complete" else status


def evaluate(directory):
    directory = Path(directory).resolve()
    terminal = read_terminal(directory)
    frozen, _ = read_control(directory)
    from ds21_evaluate import coordinates, distance_km, reference

    prior = discovery.RegionalPrior(**frozen["prior"])
    expected, rows = reference(), []
    for index, selected in enumerate(terminal["result"]["selected"]):
        point = [selected["east_km"], selected["north_km"]]
        location = coordinates(prior, point)
        rows.append(
            dict(
                proposal=index,
                point_km=point,
                coordinates_deg=list(location),
                error_km=distance_km(location, expected),
            )
        )
    value = dict(
        label=frozen["label"],
        terminal=binding(directory / "terminal.json"),
        rows=rows,
        reference_usage="After complete discovery slice, source and training-selection seal",
        held_usage="none",
        scope="Selected discovery proposal geometry only; not a downstream A/B/C result",
    )
    immutable(directory / "development-errors.json", value)
    return read(directory / "development-errors.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "evaluate"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--parent-discovery", type=Path)
    parser.add_argument("--slice-id", type=int)
    parser.add_argument("--maximum-seconds", type=float, default=480)
    args = parser.parse_args()
    if args.action == "freeze":
        if args.parent_discovery is None:
            parser.error("freeze requires --parent-discovery")
        result = freeze(args.directory, parent_discovery=args.parent_discovery)
    elif args.action == "run":
        if args.slice_id is None:
            parser.error("run requires --slice-id")
        result = run(args.directory, slice_id=args.slice_id, maximum_seconds=args.maximum_seconds)
    else:
        result = evaluate(args.directory)
    print(json.dumps(json_value(result), allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
