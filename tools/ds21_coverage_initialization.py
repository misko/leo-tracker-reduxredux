"""Qualified original initialization ports for a sealed coverage-control parent."""

import argparse
import json
import time
from pathlib import Path

import ds21_discovery_coverage as coverage
import ds21_fitted_initialization as original
import numpy as np
from ds21_common import immutable, json_value

binding, read = original.binding, original.read
STAGES = original.STAGES[1:]
CAPS = {s: original.CAPS[s] for s in STAGES}


def policy(label, stage):
    if stage not in STAGES:
        raise ValueError("Explicit downstream coverage stage required")
    return dict(
        original.policy(label, stage),
        schema="ds21-coverage-fitted-initialization-v1",
        levels_km=coverage.POLICY["levels_km"],
        discovery_schema=coverage.POLICY["schema"],
        scope="Original fitted-only initializer conditioned on coverage-control discovery",
    )


def sources():
    return {**coverage.sources(), str(Path(__file__).resolve()): binding(__file__)["sha256"]}


def authority(directory):
    return {
        str(p.relative_to(directory)): binding(p)
        for p in sorted(directory.rglob("*.json"))
        if "source-snapshot" not in p.relative_to(directory).parts
        and p.name != "development-errors.json"
    }


def coverage_parent(directory):
    directory = Path(directory).resolve()
    terminal = coverage.read_terminal(directory)
    control, inherited = coverage.read_control(directory)
    selected = terminal["result"]["selected"]
    if not terminal["result"]["available"] or len(selected) != 3:
        raise ValueError("Three original training-selected coverage proposals required")
    base = inherited["original"]
    full = base["full_bank"]
    indices = sorted(
        {i for r in selected for i in r["satellite_indices"]}, key=lambda i: full.numbers[i]
    )
    if not indices:
        raise ValueError("Required coverage candidate union unavailable")
    case = dict(base, bank=full.select(indices), discovery=terminal["result"])
    return dict(
        stage="coverage-discovery",
        directory=directory,
        case_directory=Path(control["case_directory"]),
        frozen=control,
        terminal=terminal,
        authority=authority(directory),
        original=case,
        bank=full.select(indices),
        indices=indices,
        stages={"coverage-discovery": directory},
        proposals=[dict(point_km=[r["east_km"], r["north_km"]]) for r in selected],
    )


def predecessor(stage, directory):
    if stage == "shape":
        return coverage_parent(directory)
    expected = STAGES[STAGES.index(stage) - 1]
    return read_stage(directory, expected)


def freeze_stage(directory, stage, *, parent_directory):
    if stage not in STAGES:
        raise ValueError("Explicit downstream coverage stage required")
    directory, parent_directory = Path(directory).resolve(), Path(parent_directory).resolve()
    if (directory / "protocol.json").exists():
        frozen = context(directory)[0]
        if frozen["policy"]["stage"] != stage or frozen["parent_directory"] != str(
            parent_directory
        ):
            raise ValueError("Existing coverage stage/parent differs")
        return frozen
    parent = predecessor(stage, parent_directory)
    case, source, *_ = original.read_case(parent["case_directory"])
    src = sources()
    value = dict(
        policy=policy(source["member"]["label"], stage),
        case_directory=str(parent["case_directory"]),
        case_protocol=binding(parent["case_directory"] / "protocol.json"),
        parent_directory=str(parent_directory),
        parent_authority=parent["authority"],
        coverage_terminal=binding(parent["stages"]["coverage-discovery"] / "terminal.json"),
        **{k: case[k] for k in coverage.CASE_FIELDS},
        candidate_full_indices=parent["indices"],
        candidate_numbers=parent["bank"].numbers.tolist(),
        proposals=original.stage_proposals(stage, parent),
        full_bank_count=len(parent["original"]["full_bank"].numbers),
        bank_nodes_interval_s=[float(parent["bank"].nodes_s[0]), float(parent["bank"].nodes_s[-1])],
        source_sha256=src,
        snapshot_paths=original.discovery.archive_sources(directory, src),
    )
    immutable(directory / "protocol.json", value)
    return context(directory)[0]


def context(directory):
    directory = Path(directory).resolve()
    frozen = read(directory / "protocol.json")
    stage, case_directory = frozen["policy"]["stage"], Path(frozen["case_directory"])
    case, source, member, membership, census = original.read_case(case_directory)
    if stage not in STAGES or frozen["policy"] != policy(member["label"], stage):
        raise ValueError("Coverage downstream policy changed")
    original.shape_parent.validate_archives(directory, frozen)
    if frozen["source_sha256"] != sources():
        raise ValueError("Coverage initializer scientific sources changed")
    parent = predecessor(stage, frozen["parent_directory"])
    if (
        parent["case_directory"] != case_directory
        or frozen["case_protocol"] != binding(case_directory / "protocol.json")
        or parent["authority"] != frozen["parent_authority"]
        or frozen["coverage_terminal"]
        != binding(parent["stages"]["coverage-discovery"] / "terminal.json")
        or any(frozen[k] != case[k] for k in coverage.CASE_FIELDS)
        or frozen["candidate_full_indices"] != parent["indices"]
        or frozen["candidate_numbers"] != parent["bank"].numbers.tolist()
        or frozen["full_bank_count"] != len(parent["original"]["full_bank"].numbers)
        or frozen["proposals"] != original.stage_proposals(stage, parent)
        or frozen["bank_nodes_interval_s"]
        != [float(parent["bank"].nodes_s[0]), float(parent["bank"].nodes_s[-1])]
    ):
        raise ValueError("Coverage initializer exact predecessor/case authority changed")
    return frozen, case, member, membership, census, parent


def read_stage(directory, stage=None):
    directory = Path(directory).resolve()
    frozen, _, member, _, _, parent = context(directory)
    actual = frozen["policy"]["stage"]
    if stage is not None and actual != stage:
        raise ValueError("Requested coverage stage differs")
    sha = binding(directory / "protocol.json")["sha256"]
    terminal, calls = read(directory / "terminal.json"), original.completed_calls(directory, frozen)
    if (
        terminal["protocol_sha256"] != sha
        or terminal["label"] != member["label"]
        or terminal["stage"] != actual
        or terminal["arm"] != "fitted-c"
        or terminal["state"] != "complete"
        or terminal["reference_usage"] != "none"
        or terminal["held_usage"] != "none"
        or not original.check_slices(directory, sha)
        or set(calls) != set(original.identifiers(actual))
        or terminal["calls"] != {k: binding(directory / "calls" / f"{k}.json") for k in calls}
    ):
        raise ValueError("Coverage downstream stage completion changed")
    expected_artifacts = (
        set()
        if actual == "shape"
        else {"hybrid-result.json"}
        if actual == "hybrid"
        else {"candidate-pool.json", *(f"seeds/{v}.json" for v in original.VIEWS)}
    )
    if set(terminal["artifacts"]) != expected_artifacts:
        raise ValueError("Coverage stage artifact inventory changed")
    for name, claim in terminal["artifacts"].items():
        if claim != binding(directory / name):
            raise ValueError("Coverage stage artifact binding changed")
    full, indices, proposals = (
        parent["original"]["full_bank"],
        frozen["candidate_full_indices"],
        frozen["proposals"],
    )
    if actual in ("shape-bootstrap", "cold-bootstrap", "six-proposals"):
        pool = read(directory / "candidate-pool.json")
        indices = pool["candidate_full_indices"]
        if (
            pool["candidate_numbers"] != full.numbers[indices].tolist()
            or pool["proposals"] != proposals
            or indices != sorted(set(indices), key=lambda i: full.numbers[i])
            or (actual != "shape-bootstrap" and indices != frozen["candidate_full_indices"])
        ):
            raise ValueError("Coverage downstream candidate pool changed")
        if actual == "shape-bootstrap":
            receipts = [read(directory / "bootstrap" / f"proposal-{i}.json") for i in range(3)]
            if indices != list(
                original.fresh.candidate_union(
                    frozen["candidate_full_indices"], receipts, full.numbers
                )
            ):
                raise ValueError("Coverage fresh candidate union changed")
        for view in original.VIEWS:
            entries = read(directory / "seeds" / f"{view}.json")
            if len(entries) != (6 if actual == "six-proposals" else 3):
                raise ValueError("Coverage physical source count changed")
            for index, entry in enumerate(entries):
                vector, nuisance = np.asarray(entry["vector"]), np.asarray(entry["nuisance"])
                groups = len(frozen["training_frames"][view]["receivers"])
                if (
                    vector.shape != (7 + len(indices),)
                    or nuisance.shape != (2 * (len(frozen["clock_nodes_s"]) - 2) + groups,)
                    or not np.isfinite(vector).all()
                    or not np.isfinite(nuisance).all()
                    or vector[:2].tolist() != proposals[index]["point_km"]
                ):
                    raise ValueError("Coverage physical seed layout changed")
                if actual == "six-proposals" and (
                    entry["proposal_id"] != original.PROPOSAL_IDS[index]
                    or entry["orbit_timing"]["satellite_numbers"] != full.numbers[indices].tolist()
                    or entry["physical_correction_kind"]
                    != "training-derived-initialization-function"
                    or not 0 <= entry["source_closure_max_abs_hz"] <= 1e-6
                ):
                    raise ValueError("Coverage six-source physical export changed")
    if actual == "shape" and terminal["rows"] != [calls[v]["result"] for v in original.VIEWS]:
        raise ValueError("Coverage fitted shape rows changed")
    if actual == "hybrid" and read(directory / "hybrid-result.json") != original.hybrid_result(
        calls
    ):
        raise ValueError("Coverage fitted hybrid selector changed")
    stages = dict(parent["stages"], **{actual: directory})
    return dict(
        stage=actual,
        directory=directory,
        case_directory=Path(frozen["case_directory"]),
        frozen=frozen,
        terminal=terminal,
        authority=authority(directory),
        original=parent["original"],
        bank=full.select(indices),
        indices=indices,
        stages=stages,
        proposals=proposals,
    )


def run_stage(directory, stage, *, slice_id, maximum_seconds=None):
    directory = Path(directory).resolve()
    if stage not in STAGES or type(slice_id) is not int or slice_id < 0:
        raise ValueError("Explicit downstream stage and nonnegative slice required")
    cap = CAPS[stage] if maximum_seconds is None else maximum_seconds
    if not np.isfinite(cap) or not 0 < cap <= CAPS[stage]:
        raise ValueError("Coverage stage exceeds original slice bound")
    begun = time.monotonic()
    frozen, case_frozen, member, membership, census, parent = context(directory)
    if frozen["policy"]["stage"] != stage:
        raise ValueError("Requested coverage stage differs")
    sha = binding(directory / "protocol.json")["sha256"]
    rows = original.completed_calls(directory, frozen)
    original.check_slices(directory, sha)
    if (directory / "terminal.json").exists():
        return read_stage(directory, stage)["terminal"]
    launch = directory / "slices" / f"{slice_id:03d}-launch.json"
    launch.parent.mkdir(parents=True, exist_ok=True)
    identity = dict(protocol_sha256=sha, slice_id=slice_id)
    with launch.open("x") as stream:
        json.dump(identity, stream)
    status = dict(identity, state="failed")
    try:
        with original.discovery.slice_bound(max(0.001, cap - (time.monotonic() - begun))):
            case = original.discovery.prepare_training_case(member, membership, census)
            original.discovery.validate_preparation(case, case_frozen)
            case.update(
                full_bank=parent["original"]["full_bank"],
                bank=parent["original"]["bank"],
                discovery=parent["original"]["discovery"],
            )
            for name in original.identifiers(stage):
                if name in rows:
                    continue
                cost = 60 if stage == "shape" else 20 if stage == "hybrid" else 5
                if time.monotonic() - begun + cost + 10 >= cap:
                    status.update(state="checkpointed", next_call=name)
                    return dict(status, completed_calls=len(rows))
                call_identity = dict(
                    protocol_sha256=sha,
                    label=member["label"],
                    stage=stage,
                    name=name,
                    arm="fitted-c",
                )
                call_launch = directory / "launches" / f"{name}.json"
                call_launch.parent.mkdir(parents=True, exist_ok=True)
                with call_launch.open("x") as stream:
                    json.dump(call_identity, stream)
                value = None
                try:
                    value = json.loads(
                        json.dumps(
                            json_value(original.operation(stage, name, case, parent, frozen)),
                            allow_nan=False,
                        )
                    )
                    original.validate_value(value, stage, name, frozen)
                    row = dict(identity=call_identity, state="complete", result=value)
                except (ValueError, TimeoutError) as error:
                    row = dict(
                        identity=call_identity,
                        state="failed",
                        reason=str(error),
                        error_type=type(error).__name__,
                    )
                    if value is not None:
                        row["invalid_result"] = value
                path = directory / "calls" / f"{name}.json"
                immutable(path, row)
                immutable(
                    directory / "terminations" / path.name, dict(call_identity, row=binding(path))
                )
                rows[name] = read(path)
            artifacts = original.assemble(directory, stage, case, parent, frozen, rows)
            extra = {}
            if stage == "shape":
                if any(rows[v]["state"] != "complete" for v in original.VIEWS):
                    raise ValueError("Required fitted coverage shape view failed")
                extra["rows"] = [rows[v]["result"] for v in original.VIEWS]
            context(directory)
            immutable(
                directory / "terminal.json",
                dict(
                    state="complete",
                    label=member["label"],
                    stage=stage,
                    arm="fitted-c",
                    protocol_sha256=sha,
                    calls={k: binding(directory / "calls" / f"{k}.json") for k in rows},
                    artifacts=artifacts,
                    reference_usage="none",
                    held_usage="none",
                    elapsed_s=time.monotonic() - begun,
                    **extra,
                ),
            )
            status["state"] = "complete"
    except original.discovery.DiscoverySliceExpired as error:
        status.update(state="checkpointed", next_call=str(error))
        return status
    except BaseException as error:
        status.update(reason=str(error), error_type=type(error).__name__)
        raise
    finally:
        status["elapsed_s"] = time.monotonic() - begun
        immutable(launch.with_name(launch.name.replace("-launch", "-termination")), status)
    return read_stage(directory, stage)["terminal"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze-stage", "run-stage", "read-stage"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--parent-directory", type=Path)
    parser.add_argument("--slice-id", type=int)
    parser.add_argument("--maximum-seconds", type=float)
    args = parser.parse_args()
    if args.command == "freeze-stage":
        if args.parent_directory is None:
            parser.error("freeze-stage requires --parent-directory")
        result = freeze_stage(args.directory, args.stage, parent_directory=args.parent_directory)
    elif args.command == "run-stage":
        if args.slice_id is None:
            parser.error("run-stage requires --slice-id")
        result = run_stage(
            args.directory, args.stage, slice_id=args.slice_id, maximum_seconds=args.maximum_seconds
        )
    else:
        result = read_stage(args.directory, args.stage)["terminal"]
    print(json.dumps(json_value(result), allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
