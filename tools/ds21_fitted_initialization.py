"""One explicit fitted-only initialization stage for any fast DS21 development case.

Existing DS21-007 coordinators and their source archives remain unchanged.
Only label-neutral metadata/numerical ports are reused. This module never
prepares held windows, accesses the reference, or launches a case campaign.
"""

import argparse
import ast
import json
import time
from dataclasses import asdict
from pathlib import Path

import ds21_fitted_discovery as discovery
import ds21_fitted_proposals as shape_parent
import ds21_shape as shape
import ds21_shape_cold_seed_control as cold
import ds21_shape_fresh_seeds as fresh
import numpy as np
from ds21_common import OUTPUT, immutable, json_value

from leo.analysis.channel_group_calibration import fit_group_calibration, group_frame
from leo.analysis.channel_group_seeds import shared_bootstrap_seed
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.regional_position_bootstrap import PositionBootstrap
from leo.analysis.regional_position_score import ALIAS_HZ, zero_sum_basis
from leo.analysis.research.doppler_shape_orbits import DopplerShapeOrbitObjective, fit_doppler_shape
from leo.analysis.research.doppler_shape_shared_proposals import (
    PROPOSAL_IDS,
    encode_initial_physical_seed,
    ordered_seed_entries,
)
from leo.application.channel_group_refinement import objective

STAGES = ("discovery", "shape", "shape-bootstrap", "hybrid", "cold-bootstrap", "six-proposals")
VIEWS = ("all", "low", "high")
CAPS = dict(zip(STAGES, (480, 240, 90, 240, 90, 90), strict=True))
NUMERIC = dict(
    partition_seed=20261012,
    block_seconds=20,
    points=100,
    levels_km=[100.0, 50.0, 25.0, 12.5],
    priority_view="all",
    bootstrap_seconds=5,
    fixed_position_fit_seconds=5,
    fixed_position_fit_iterations=200,
    bank_seconds=180,
    point_admission_reserve_seconds=31,
)
binding, read, read_bound = shape_parent.binding, shape_parent.read, shape_parent.read_bound


def inherited_gates():
    if any(discovery.POLICY.get(k) != v for k, v in NUMERIC.items()):
        raise ValueError("Inherited discovery numeric constants changed")
    if any(
        shape_parent.POLICY.get(k) != v
        for k, v in dict(
            fit_seconds=20,
            iterations=600,
            sigma_hz=400.0,
            timing_sigma_s=2.0,
        ).items()
    ):
        raise ValueError("Inherited fitted shape numeric constants changed")


def policy(label, stage):
    return dict(
        schema="ds21-generic-fitted-initialization-v1",
        label=label,
        stage=stage,
        arm="fitted-c",
        views=list(VIEWS),
        internal_seconds=CAPS.get(stage, 60),
        external_term_seconds=CAPS.get(stage, 60) + 15,
        external_kill_seconds=CAPS.get(stage, 60) + 20,
        failed_retry=False,
        fit_seconds=20,
        iterations=600,
        local_radius_km=25,
        held_usage="none",
        reference_usage="none",
        **NUMERIC,
    )


def sources():
    """Deterministic reachable closure; consumers cannot add ambient dependencies."""
    from leo.analysis import _regional_orbits

    root = Path(__file__).resolve().parents[1]
    pending, seen = [Path(__file__).resolve(), discovery.ADAPTER.resolve()], set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        modules = []
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    base = root / ("src" if path.is_relative_to(root / "src") else "tools")
                    package = list(path.relative_to(base).parts[:-1])
                    module = ".".join(
                        package[: len(package) - node.level + 1] + ([module] if module else [])
                    )
                modules.append(module)
                modules.extend(f"{module}.{alias.name}" for alias in node.names)
        for module in modules:
            parts = module.split(".")
            base = root / ("src" if parts[0] == "leo" else "tools")
            target = base.joinpath(*parts).with_suffix(".py")
            if target.exists():
                pending.append(target.resolve())
            for length in range(1, len(parts) + 1):
                package = base.joinpath(*parts[:length]) / "__init__.py"
                if package.exists():
                    pending.append(package.resolve())
    seen.update(
        (Path(_regional_orbits.__file__).resolve(), root / "src/leo/analysis/_regional_orbits.cpp")
    )
    return {str(path): binding(path)["sha256"] for path in sorted(seen)}


def inventory(label, membership_path, census_path):
    membership, census = read(membership_path), read(census_path)
    eligible = [
        m
        for m in membership["members"]
        if m["role"] == "development" and m["eight_channel"] and m["session_id"].startswith("fast-")
    ]
    members = [m for m in eligible if m["label"] == label]
    if len(members) != 1 or members[0]["channels"] != list(range(1, 9)):
        raise ValueError(
            "Original fast eight-channel development member required; evaluation refused"
        )
    member = members[0]
    if (
        census["membership_sha256"] != binding(membership_path)["sha256"]
        or census["label"] != label
        or census["role"] != "development"
        or census["state"] != "prepared"
        or member["input"] is None
    ):
        raise ValueError("Label-specific original census/input authority differs")
    if binding(member["input"]["path"]) != member["input"]:
        raise ValueError("Original tracking input changed")
    return member, membership, census, sorted(m["label"] for m in eligible)


def freeze_case(
    directory,
    label,
    *,
    membership_path=OUTPUT / "membership.json",
    census_path=None,
    tle_root=Path("/var/lib/leo/tle"),
):
    inherited_gates()
    directory = Path(directory).resolve()
    census_path = (
        Path(census_path)
        if census_path
        else Path(membership_path).parent / "local/census" / f"{label}.json"
    )
    member, membership, census, eligible = inventory(label, membership_path, census_path)
    if (directory / "protocol.json").exists():
        return read_case(directory)[0]
    source = sources()
    immutable(
        directory / "source-protocol.json",
        dict(
            policy=policy(label, "case"),
            member=member,
            membership=binding(membership_path),
            census=binding(census_path),
            input=member["input"],
            eligible_labels=eligible,
            source_sha256=source,
            snapshot_paths=discovery.archive_sources(directory, source),
        ),
    )
    launch, done = directory / "preparation-launch.json", directory / "preparation-termination.json"
    if launch.exists() or done.exists():
        raise ValueError("Orphan/failed case preparation; no retry")
    identity = dict(label=label, source_protocol=binding(directory / "source-protocol.json"))
    with launch.open("x") as stream:
        json.dump(identity, stream)
    status = dict(**identity, state="failed")
    try:
        with discovery.slice_bound(60):
            case = discovery.prepare_training_case(member, membership, census)
            archive = discovery.TleArchiveReader(Path(tle_root))
            snapshot = archive.select_latest_before(case["prepared"]["all"].start_utc_ns)
            archive.read(snapshot)
            frozen = dict(
                policy=policy(label, "case"),
                source_protocol=identity["source_protocol"],
                start_utc_ns=case["prepared"]["all"].start_utc_ns,
                prepared={v: p.evidence_sha256 for v, p in case["prepared"].items()},
                prior=asdict(case["prior"]),
                clock_nodes_s=case["nodes"].tolist(),
                partition=dict(
                    seed=case["split"].seed,
                    block_seconds=case["split"].block_seconds,
                    held_blocks=list(case["split"].held_blocks),
                    assignments=[list(a) for a in case["split"].assignments],
                ),
                training_frames={
                    v: dict(
                        time_center_s=p.observations.time_center_s,
                        rf_center_hz=p.observations.rf_center_hz,
                        minimum_time_s=float(p.observations.times_s.min()),
                        maximum_time_s=float(p.observations.times_s.max()),
                        **asdict(group_frame(p.observations.receiver, p.observations.channel >= 5)),
                    )
                    for v, p in case["prepared"].items()
                },
                snapshot=dict(
                    path=str(snapshot.path.resolve()),
                    sha256=snapshot.digest,
                    provider=snapshot.provider,
                    collected_utc_ns=snapshot.collected_utc_ns,
                    byte_size=snapshot.byte_size,
                    archive_root=str(Path(tle_root).resolve()),
                ),
            )
            immutable(directory / "protocol.json", frozen)
            status = dict(
                **identity, protocol=binding(directory / "protocol.json"), state="complete"
            )
    except BaseException as error:
        status.update(reason=str(error), error_type=type(error).__name__)
        raise
    finally:
        immutable(done, status)
    return read_case(directory)[0]


def read_case(directory):
    inherited_gates()
    directory = Path(directory).resolve()
    frozen, source = read(directory / "protocol.json"), read(directory / "source-protocol.json")
    label = source["member"]["label"]
    shape_parent.validate_archives(directory, source)
    if any(source["source_sha256"].get(p) != sha for p, sha in sources().items()):
        raise ValueError("Case scientific source closure changed")
    member, membership, census, eligible = inventory(
        label, source["membership"]["path"], source["census"]["path"]
    )
    identity = dict(label=label, source_protocol=binding(directory / "source-protocol.json"))
    if (
        source["policy"] != policy(label, "case")
        or frozen["policy"] != source["policy"]
        or frozen["source_protocol"] != identity["source_protocol"]
        or source["member"] != member
        or source["eligible_labels"] != eligible
        or source["input"] != member["input"]
        or frozen["prior"] != membership["prior"]
        or read(directory / "preparation-launch.json") != identity
        or read(directory / "preparation-termination.json")
        != dict(**identity, protocol=binding(directory / "protocol.json"), state="complete")
    ):
        raise ValueError("Case source/member/preparation authority changed")
    for key in ("membership", "census", "input"):
        read_bound(source[key])
    snapshot = frozen["snapshot"]
    if (
        snapshot["collected_utc_ns"] >= frozen["start_utc_ns"]
        or binding(snapshot["path"])["sha256"] != snapshot["sha256"]
    ):
        raise ValueError("Case catalogue changed or is noncausal")
    return frozen, source, member, membership, census


def authority(directory):
    return {
        str(p.relative_to(directory)): binding(p)
        for p in sorted(directory.rglob("*.json"))
        if "source-snapshot" not in p.relative_to(directory).parts
    }


def stage_proposals(stage, parent):
    if stage == "shape-bootstrap":
        return shape_parent.fitted_shape_proposals(parent["terminal"])
    if stage == "cold-bootstrap":
        return [
            dict(start=i, point_km=[r["east_km"], r["north_km"]])
            for i, r in enumerate(parent["original"]["discovery"]["selected"])
        ]
    if stage == "six-proposals":
        shapes = read(parent["stages"]["shape-bootstrap"] / "candidate-pool.json")["proposals"]
        return [
            dict(
                proposal_id=PROPOSAL_IDS[i],
                id=PROPOSAL_IDS[i],
                source_kind="cold",
                source_start=i,
                point_km=p["point_km"],
            )
            for i, p in enumerate(parent["proposals"])
        ] + [
            dict(
                proposal_id=PROPOSAL_IDS[i + 3],
                id=PROPOSAL_IDS[i + 3],
                source_kind="shape",
                source_view=p["source_view"],
                source_start=i,
                point_km=p["point_km"],
            )
            for i, p in enumerate(shapes)
        ]
    return parent["proposals"]


def freeze_stage(directory, stage, *, parent_directory):
    if stage not in STAGES:
        raise ValueError("Explicit known initialization stage required")
    directory, parent_directory = Path(directory).resolve(), Path(parent_directory).resolve()
    if stage == "discovery":
        case_directory, parent, parent_bindings = parent_directory, None, {}
    else:
        parent = read_stage(parent_directory)
        if parent["stage"] != STAGES[STAGES.index(stage) - 1]:
            raise ValueError("Exact completed predecessor stage required")
        case_directory, parent_bindings = parent["case_directory"], parent["authority"]
    frozen, source, *_ = read_case(case_directory)
    value = dict(
        policy=policy(source["member"]["label"], stage),
        case_directory=str(case_directory),
        case_protocol=binding(case_directory / "protocol.json"),
        parent_directory=str(parent_directory),
        parent_authority=parent_bindings,
        **{
            k: frozen[k]
            for k in (
                "start_utc_ns",
                "prepared",
                "prior",
                "partition",
                "training_frames",
                "clock_nodes_s",
                "snapshot",
            )
        },
    )
    if parent is not None:
        value.update(
            candidate_full_indices=parent["indices"],
            candidate_numbers=parent["bank"].numbers.tolist(),
            proposals=stage_proposals(stage, parent),
            full_bank_count=len(parent["original"]["full_bank"].numbers),
            bank_nodes_interval_s=[
                float(parent["bank"].nodes_s[0]),
                float(parent["bank"].nodes_s[-1]),
            ],
        )
    immutable(directory / "protocol.json", value)
    return read(directory / "protocol.json")


def identifiers(stage):
    if stage in ("discovery", "six-proposals"):
        return []
    return list(VIEWS) if stage == "shape" else [f"{i}-{v}" for i in range(3) for v in VIEWS]


def completed_calls(directory, frozen):
    sha, stage = binding(directory / "protocol.json")["sha256"], frozen["policy"]["stage"]
    names, rows = set(identifiers(stage)), {}
    for folder in ("calls", "launches", "terminations"):
        if not {p.stem for p in (directory / folder).glob("*.json")} <= names:
            raise ValueError("Extra stage call or forbidden arm")
    for name in identifiers(stage):
        path = directory / "calls" / f"{name}.json"
        launch, done = directory / "launches" / path.name, directory / "terminations" / path.name
        identity = dict(
            protocol_sha256=sha,
            label=frozen["policy"]["label"],
            stage=stage,
            name=name,
            arm="fitted-c",
        )
        if path.exists():
            row = read(path)
            if (
                not launch.exists()
                or not done.exists()
                or read(launch) != identity
                or read(done) != dict(**identity, row=binding(path))
                or row["identity"] != identity
                or row["state"] not in ("complete", "failed")
            ):
                raise ValueError("Stage call identity/completion changed")
            if row["state"] == "complete":
                validate_value(row["result"], stage, name, frozen)
            rows[name] = row
        elif launch.exists() or done.exists():
            raise ValueError("Orphan stage call; no retry")
    return rows


def validate_value(value, stage, name, frozen):
    if stage == "shape":
        fits = value["attempts"]
        eligible = [f for f in fits if f["stationary"]]
        expected = min(eligible, key=lambda f: f["objective"]) if eligible else None
        if (
            value["rf_arm"] != "fitted-c"
            or len(fits) != 3
            or value["winner"] != expected
            or value["label"] != frozen["policy"]["label"]
            or value["view"] != name
            or value["prepared_sha256"] != frozen["prepared"][name]
        ):
            raise ValueError("Fitted shape training selector changed")
        for fit in fits:
            theta = np.asarray(fit["theta"])
            frame = frozen["training_frames"][name]
            lower = max(-10.0, frozen["bank_nodes_interval_s"][0] - frame["minimum_time_s"])
            upper = min(10.0, frozen["bank_nodes_interval_s"][1] - frame["maximum_time_s"])
            if (
                theta.shape != (4,)
                or not np.isfinite(theta).all()
                or (
                    fit["stationary"]
                    and (
                        fit["stationarity"] > 0.001
                        or not np.isfinite(fit["objective"])
                        or abs(theta[3]) > 5000 + 1e-7
                        or not np.isfinite(fit["stationarity"])
                        or not lower - 1e-7 <= theta[2] <= upper + 1e-7
                        or np.hypot(*theta[:2]) > frozen["prior"]["radius_km"] + 1e-7
                    )
                )
            ):
                raise ValueError("Fitted shape state changed")
        return
    index, view = name.split("-", 1)
    v = np.asarray(value["vector"])
    indices = value["satellite_indices"] if stage != "hybrid" else frozen["candidate_full_indices"]
    if (
        not indices
        or len(indices) != len(set(indices))
        or any(type(i) is not int or not 0 <= i < frozen["full_bank_count"] for i in indices)
        or v.shape != (7 + len(indices),)
        or not np.isfinite(v).all()
        or abs(v[6]) > 5000 + 1e-7
        or abs(v[7]) > 10 + 1e-7
    ):
        raise ValueError("Stage bootstrap/fit layout changed")
    if stage != "hybrid":
        if v[:2].tolist() != frozen["proposals"][int(index)]["point_km"]:
            raise ValueError("Bootstrap source point changed")
        if stage == "cold-bootstrap" and not set(indices) <= set(frozen["candidate_full_indices"]):
            raise ValueError("Cold bootstrap added candidates")
    else:
        n = np.asarray(value["nuisance"])
        frame = frozen["training_frames"][view]
        clocks = 2 * (len(frozen["clock_nodes_s"]) - 2)
        shifts = v[7] + zero_sum_basis(len(indices)) @ v[8:]
        lower = max(-20.0, frozen["bank_nodes_interval_s"][0] - frame["minimum_time_s"])
        upper = min(20.0, frozen["bank_nodes_interval_s"][1] - frame["maximum_time_s"])
        if (
            n.shape != (2 * (len(frozen["clock_nodes_s"]) - 2) + len(frame["receivers"]),)
            or not np.isfinite(n).all()
            or np.max(abs(n[:clocks]), initial=0) > 2000 + 1e-7
            or np.max(abs(n[clocks:]), initial=0) > ALIAS_HZ / 2 + 1e-7
            or np.max(abs(v[[3, 5]])) > 60 + 1e-7
            or shifts.min() < lower - 1e-7
            or shifts.max() > upper + 1e-7
            or np.hypot(*v[:2]) > frozen["prior"]["radius_km"] + 1e-7
            or value["group_receivers"] != frame["receivers"]
            or value["training_high_fractions"] != frame["high_fractions"]
            or value["training_time_center_s"] != frame["time_center_s"]
            or value["training_rf_center_hz"] != frame["rf_center_hz"]
            or not np.isfinite(
                [value["objective"], value["stationarity"], value["likelihood_nll"]]
            ).all()
            or value["converged"] != (value["stationarity"] <= 0.001)
            or np.linalg.norm(v[:2] - frozen["proposals"][int(index)]["point_km"]) > 25 + 1e-6
        ):
            raise ValueError("Hybrid frame/bounds/stationarity changed")


def check_slices(directory, sha):
    claims = list((directory / "slices").glob("*-launch.json"))
    expected = {p.with_name(p.name.replace("-launch", "-termination")) for p in claims}
    if set((directory / "slices").glob("*-termination.json")) != expected:
        raise ValueError("Orphan stage slice; no retry")
    complete = False
    for path in claims:
        claim, done = read(path), read(path.with_name(path.name.replace("-launch", "-termination")))
        identity = dict(protocol_sha256=sha, slice_id=claim["slice_id"])
        if (
            claim != identity
            or type(claim["slice_id"]) is not int
            or claim["slice_id"] < 0
            or path.name != f"{claim['slice_id']:03d}-launch.json"
            or any(done.get(k) != v for k, v in identity.items())
            or done["state"] not in ("checkpointed", "complete")
        ):
            raise ValueError("Failed/changed stage slice; no retry")
        complete |= done["state"] == "complete"
    return complete


def context(directory):
    frozen = read(directory / "protocol.json")
    stage, case_directory = frozen["policy"]["stage"], Path(frozen["case_directory"])
    case_frozen, source, member, membership, census = read_case(case_directory)
    if (
        stage not in STAGES
        or frozen["policy"] != policy(member["label"], stage)
        or frozen["case_protocol"] != binding(case_directory / "protocol.json")
        or any(
            frozen[k] != case_frozen[k]
            for k in (
                "prepared",
                "partition",
                "prior",
                "training_frames",
                "clock_nodes_s",
                "snapshot",
                "start_utc_ns",
            )
        )
    ):
        raise ValueError("Stage original case/preparation authority changed")
    parent = None
    if stage != "discovery":
        parent = read_stage(frozen["parent_directory"])
        if (
            parent["stage"] != STAGES[STAGES.index(stage) - 1]
            or parent["case_directory"] != case_directory
            or parent["authority"] != frozen["parent_authority"]
            or parent["indices"] != frozen["candidate_full_indices"]
            or parent["bank"].numbers.tolist() != frozen["candidate_numbers"]
            or len(parent["original"]["full_bank"].numbers) != frozen["full_bank_count"]
            or stage_proposals(stage, parent) != frozen["proposals"]
            or [float(parent["bank"].nodes_s[0]), float(parent["bank"].nodes_s[-1])]
            != frozen["bank_nodes_interval_s"]
        ):
            raise ValueError("Stage completed predecessor authority changed")
    return frozen, case_frozen, member, membership, census, parent


def read_stage(directory, stage=None):
    """Receipt/array-only authority and selector validation; no preparation/fits."""
    directory = Path(directory).resolve()
    frozen, case_frozen, member, membership, census, parent = context(directory)
    actual = frozen["policy"]["stage"]
    if stage is not None and actual != stage:
        raise ValueError("Requested stage differs")
    sha = binding(directory / "protocol.json")["sha256"]
    terminal, calls = read(directory / "terminal.json"), completed_calls(directory, frozen)
    if (
        terminal["protocol_sha256"] != sha
        or terminal["label"] != member["label"]
        or terminal["stage"] != actual
        or terminal["state"] != "complete"
        or terminal["reference_usage"] != "none"
        or terminal["held_usage"] != "none"
        or not check_slices(directory, sha)
        or set(calls) != set(identifiers(actual))
        or terminal["calls"] != {k: binding(directory / "calls" / f"{k}.json") for k in calls}
    ):
        raise ValueError("Stage terminal coverage/completion changed")
    expected_artifacts = (
        set()
        if actual == "shape"
        else {"bank.npz", "bank.json"}
        if actual == "discovery"
        else {"hybrid-result.json"}
        if actual == "hybrid"
        else {"candidate-pool.json", *(f"seeds/{v}.json" for v in VIEWS)}
    )
    if set(terminal["artifacts"]) != expected_artifacts:
        raise ValueError("Stage terminal artifact inventory changed")
    for name, receipt in terminal["artifacts"].items():
        if receipt != binding(directory / name):
            raise ValueError("Stage artifact binding changed")
    stages = {} if parent is None else dict(parent["stages"])
    stages[actual] = directory
    if actual == "discovery":
        full, _ = discovery.load_bank(directory, sha)
        if read(directory / "bank-launch.json") != dict(protocol_sha256=sha) or read(
            directory / "bank-termination.json"
        ) != dict(protocol_sha256=sha, bank=binding(directory / "bank.json")):
            raise ValueError("Bank generation completion changed")
        points = discovery.AuditedPoints(directory, sha, full, frozen, time.monotonic())
        discovery.validate_terminal(directory, frozen, full, points)
        selected = terminal["result"]["selected"]
        indices = sorted(
            {i for r in selected for i in r["satellite_indices"]}, key=lambda i: full.numbers[i]
        )
        original = dict(
            member=member,
            membership=membership,
            census=census,
            frozen=case_frozen,
            full_bank=full,
            bank=full.select(indices),
            discovery=terminal["result"],
        )
        proposals = [dict(point_km=[r["east_km"], r["north_km"]]) for r in selected]
    else:
        original, full = parent["original"], parent["original"]["full_bank"]
        indices = frozen["candidate_full_indices"]
        proposals = frozen["proposals"]
        if actual in ("shape-bootstrap", "cold-bootstrap", "six-proposals"):
            saved = read(directory / "candidate-pool.json")
            indices = saved["candidate_full_indices"]
            if (
                saved["candidate_numbers"] != full.numbers[indices].tolist()
                or saved["proposals"] != proposals
                or indices != sorted(set(indices), key=lambda i: full.numbers[i])
                or (actual != "shape-bootstrap" and indices != frozen["candidate_full_indices"])
            ):
                raise ValueError("Stage candidate pool changed")
            if actual == "shape-bootstrap":
                receipts = [read(directory / "bootstrap" / f"proposal-{i}.json") for i in range(3)]
                if indices != list(
                    fresh.candidate_union(frozen["candidate_full_indices"], receipts, full.numbers)
                ):
                    raise ValueError("Fresh candidate union changed")
        if actual == "shape" and terminal["rows"] != [calls[v]["result"] for v in VIEWS]:
            raise ValueError("Shape terminal rows changed")
        if actual == "hybrid" and read(directory / "hybrid-result.json") != hybrid_result(calls):
            raise ValueError("Hybrid training selector changed")
        if actual in ("shape-bootstrap", "cold-bootstrap", "six-proposals"):
            for view in VIEWS:
                entries = read(directory / "seeds" / f"{view}.json")
                if len(entries) != (6 if actual == "six-proposals" else 3):
                    raise ValueError("Stage physical source count changed")
                for index, entry in enumerate(entries):
                    v, n = np.asarray(entry["vector"]), np.asarray(entry["nuisance"])
                    groups = len(frozen["training_frames"][view]["receivers"])
                    if (
                        v.shape != (7 + len(indices),)
                        or n.shape != (2 * (len(frozen["clock_nodes_s"]) - 2) + groups,)
                        or not np.isfinite(v).all()
                        or not np.isfinite(n).all()
                        or v[:2].tolist() != proposals[index]["point_km"]
                    ):
                        raise ValueError("Stage physical seed layout changed")
                    if actual == "six-proposals" and (
                        entry["proposal_id"] != PROPOSAL_IDS[index]
                        or entry["orbit_timing"]["satellite_numbers"]
                        != full.numbers[indices].tolist()
                        or entry["physical_correction_kind"]
                        != "training-derived-initialization-function"
                        or not 0 <= entry["source_closure_max_abs_hz"] <= 1e-6
                    ):
                        raise ValueError("Six-source physical export closure changed")
    return dict(
        stage=actual,
        directory=directory,
        case_directory=Path(frozen["case_directory"]),
        frozen=frozen,
        terminal=terminal,
        authority=authority(directory),
        original=original,
        bank=full.select(indices),
        indices=indices,
        stages=stages,
        proposals=proposals,
    )


def hybrid_result(rows):
    results = {}
    for view in VIEWS:
        attempts = [dict(start=i, outcome=rows[f"{i}-{view}"]) for i in range(3)]
        eligible = [
            r
            for r in attempts
            if r["outcome"]["state"] == "complete" and r["outcome"]["result"]["converged"]
        ]
        results[view] = dict(
            attempts=attempts,
            selected=min(eligible, key=lambda r: (r["outcome"]["result"]["objective"], r["start"]))
            if eligible
            else None,
        )
    return results


def bootstrap_receipts(directory, rows, points):
    receipts = []
    for index, proposal in enumerate(points):
        receipt = dict(point_km=proposal["point_km"], hypotheses={}, failures={})
        for view in VIEWS:
            row = rows[f"{index}-{view}"]
            if row["state"] == "complete":
                receipt["hypotheses"][view] = row["result"]
            else:
                receipt["failures"][view] = row["reason"]
        immutable(directory / "bootstrap" / f"proposal-{index}.json", receipt)
        if not receipt["hypotheses"]:
            raise ValueError("Required bootstrap proposal unavailable")
        receipts.append(receipt)
    return receipts


def operation(stage, name, case, parent, frozen):
    if stage == "shape":
        prepared = case["prepared"][name]
        sequences = shape.supported_sequences(prepared.observations, prepared.bootstrap_tracks)
        if not sequences:
            raise ValueError("Required original shape support unavailable")
        model = DopplerShapeOrbitObjective(
            prepared.observations, parent["bank"], case["prior"], sequences
        )
        result = fit_doppler_shape(
            model,
            [p["point_km"] for p in frozen["proposals"]],
            rf_arm="fitted-c",
            maximum_seconds=20,
            maximum_iterations=600,
        )
        result.update(
            view=name, label=frozen["policy"]["label"], prepared_sha256=frozen["prepared"][name]
        )
        return result
    index, view = name.split("-", 1)
    point, prepared = frozen["proposals"][int(index)]["point_km"], case["prepared"][view]
    if stage == "shape-bootstrap":
        return asdict(
            fresh.bootstrap_position(
                prepared.observations,
                case["full_bank"],
                case["prior"],
                point,
                prepared.bootstrap_tracks,
                maximum_seconds=5.0,
                orbit_predictor=fresh.predict_orbits,
            )
        )
    if stage == "cold-bootstrap":
        return asdict(
            cold.fixed_pool_bootstrap(
                prepared.observations,
                case["full_bank"],
                case["prior"],
                point,
                prepared.bootstrap_tracks,
                frozen["candidate_full_indices"],
            )
        )
    bank = case["full_bank"].select(frozen["candidate_full_indices"])
    model = objective(prepared, bank, case["prior"], case["nodes"])
    seed = read(parent["stages"]["shape-bootstrap"] / "seeds" / f"{view}.json")[int(index)]
    result = fit_group_calibration(
        model,
        np.array(seed["vector"], float, copy=True),
        seed["nuisance"],
        arm="fitted-c",
        seconds=20.0,
        iterations=600,
        local_center=point,
        local_radius_km=25.0,
    )
    freeze_group_calibration(model, result)
    return result


def assemble(directory, stage, case, parent, frozen, rows):
    if stage == "shape":
        return {}
    if stage == "hybrid":
        immutable(directory / "hybrid-result.json", hybrid_result(rows))
        return {"hybrid-result.json": binding(directory / "hybrid-result.json")}
    indices = frozen["candidate_full_indices"]
    bank = case["full_bank"].select(indices)
    if stage == "shape-bootstrap":
        bootstrap_receipts(directory, rows, frozen["proposals"])
        # All nine calls are already sealed: this public port only assembles
        # its original union, donor ordering and projected physical seeds.
        fresh.fresh_seed_pool(case, frozen["proposals"], directory)
    else:
        immutable(
            directory / "candidate-pool.json",
            dict(
                candidate_full_indices=indices,
                candidate_numbers=bank.numbers.tolist(),
                proposals=frozen["proposals"],
                reference_usage="none",
            ),
        )
        fresh_directory = parent["stages"]["shape-bootstrap"]
        if stage == "cold-bootstrap":
            receipts = bootstrap_receipts(directory, rows, frozen["proposals"])
            donors = read(fresh_directory / "seeds/all.json")
            seeds = {v: [] for v in VIEWS}
            for receipt in receipts:
                hypotheses = {
                    v: (
                        PositionBootstrap(
                            tuple(r["satellite_indices"]), np.asarray(r["vector"]), ()
                        ),
                        case["prepared"][v].observations,
                    )
                    for v, r in receipt["hypotheses"].items()
                }
                nearest = min(
                    donors,
                    key=lambda d: np.sum((np.asarray(d["vector"][:2]) - receipt["point_km"]) ** 2),
                )
                vector = np.asarray(nearest["vector"])
                fallback = dict(
                    zip(indices, vector[7] + zero_sum_basis(len(indices)) @ vector[8:], strict=True)
                )
                for view in VIEWS:
                    model = objective(case["prepared"][view], bank, case["prior"], case["nodes"])
                    seeds[view].append(
                        shared_bootstrap_seed(model, indices, hypotheses, fallback_timings=fallback)
                    )
        else:
            seeds = {}
            for view in VIEWS:
                model = objective(case["prepared"][view], bank, case["prior"], case["nodes"])
                entries = ordered_seed_entries(
                    read(parent["stages"]["cold-bootstrap"] / "seeds" / f"{view}.json"),
                    read(fresh_directory / "seeds" / f"{view}.json"),
                    frozen["proposals"],
                )
                for entry in entries:
                    entry.update(
                        encode_initial_physical_seed(model, entry["vector"], entry["nuisance"])
                    )
                seeds[view] = entries
        for view, values in seeds.items():
            immutable(directory / "seeds" / f"{view}.json", values)
    return {
        name: binding(directory / name)
        for name in ("candidate-pool.json", *(f"seeds/{v}.json" for v in VIEWS))
    }


def run_discovery(directory, frozen, case, begun, maximum_seconds):
    sha = binding(directory / "protocol.json")["sha256"]
    if (directory / "bank.json").exists():
        bank, _ = discovery.load_bank(directory, sha)
    else:
        if (directory / "bank-launch.json").exists() or (directory / "bank.npz").exists():
            raise ValueError("Orphan bank generation; no retry")
        snapshot = frozen["snapshot"]
        ref = discovery.TleSnapshotRef(
            snapshot["collected_utc_ns"],
            snapshot["provider"],
            snapshot["sha256"].removeprefix("sha256:"),
            snapshot["byte_size"],
            Path(snapshot["path"]),
        )
        catalogue = discovery.parse_element_sets(
            discovery.TleArchiveReader(Path(snapshot["archive_root"])).read(ref)
        )
        indices = [
            i
            for i, n in enumerate(catalogue.names)
            if n.upper().startswith("STARLINK") and "DEB" not in n.upper()
        ]
        immutable(directory / "bank-launch.json", dict(protocol_sha256=sha))
        bank, receipt = discovery.build_regional_bank(
            catalogue,
            indices,
            frozen["start_utc_ns"],
            case["envelope"],
            case["prior"],
            maximum_seconds=min(180, maximum_seconds - (time.monotonic() - begun)),
        )
        with (directory / "bank.npz").open("xb") as stream:
            np.savez(
                stream,
                **{
                    k: getattr(bank, k)
                    for k in ("numbers", "nodes_s", "position_km", "velocity_km_s")
                },
            )
        immutable(
            directory / "bank.json",
            dict(protocol_sha256=sha, bank=binding(directory / "bank.npz"), build=asdict(receipt)),
        )
        immutable(
            directory / "bank-termination.json",
            dict(protocol_sha256=sha, bank=binding(directory / "bank.json")),
        )
    if read(directory / "bank-launch.json") != dict(protocol_sha256=sha) or read(
        directory / "bank-termination.json"
    ) != dict(protocol_sha256=sha, bank=binding(directory / "bank.json")):
        raise ValueError("Bank generation completion changed")
    points = discovery.AuditedPoints(directory, sha, bank, frozen, begun + maximum_seconds)
    points.completed()
    result = discovery.discover_channel_groups(
        case["prepared"],
        bank,
        case["prior"],
        points,
        maximum_seconds=maximum_seconds - (time.monotonic() - begun),
        points=100,
        clock_nodes=case["nodes"],
        levels_km=NUMERIC["levels_km"],
        priority_view="all",
    )
    return dict(
        result=result,
        protocol=binding(directory / "protocol.json"),
        bank=binding(directory / "bank.json"),
        points={k: binding(points.path(k)) for k in points.completed()},
    )


def run_stage(directory, stage, *, slice_id, maximum_seconds=None):
    directory = Path(directory).resolve()
    if stage not in STAGES or type(slice_id) is not int or slice_id < 0:
        raise ValueError("Explicit known stage and nonnegative slice required")
    cap = CAPS[stage] if maximum_seconds is None else maximum_seconds
    if not np.isfinite(cap) or not 0 < cap <= CAPS[stage]:
        raise ValueError("Stage exceeds original slice bound")
    begun = time.monotonic()
    frozen, case_frozen, member, membership, census, parent = context(directory)
    if frozen["policy"]["stage"] != stage:
        raise ValueError("Requested stage differs")
    sha = binding(directory / "protocol.json")["sha256"]
    rows = completed_calls(directory, frozen)
    check_slices(directory, sha)
    if (directory / "terminal.json").exists():
        return read_stage(directory, stage)["terminal"]
    launch = directory / "slices" / f"{slice_id:03d}-launch.json"
    launch.parent.mkdir(parents=True, exist_ok=True)
    identity = dict(protocol_sha256=sha, slice_id=slice_id)
    with launch.open("x") as stream:
        json.dump(identity, stream)
    status = dict(**identity, state="failed")
    try:
        with discovery.slice_bound(max(0.001, cap - (time.monotonic() - begun))):
            case = discovery.prepare_training_case(member, membership, census)
            discovery.validate_preparation(case, case_frozen)
            extra, artifacts = {}, {}
            if stage == "discovery":
                extra = run_discovery(directory, frozen, case, begun, cap)
                artifacts = {name: binding(directory / name) for name in ("bank.npz", "bank.json")}
            else:
                case.update(
                    full_bank=parent["original"]["full_bank"],
                    bank=parent["original"]["bank"],
                    discovery=parent["original"]["discovery"],
                )
                for name in identifiers(stage):
                    if name in rows:
                        continue
                    cost = 60 if stage == "shape" else 20 if stage == "hybrid" else 5
                    if time.monotonic() - begun + cost + 10 >= cap:
                        status.update(state="checkpointed", next_call=name)
                        return dict(**status, completed_calls=len(rows))
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
                    try:
                        value = json.loads(
                            json.dumps(
                                json_value(operation(stage, name, case, parent, frozen)),
                                allow_nan=False,
                            )
                        )
                        validate_value(value, stage, name, frozen)
                        row = dict(identity=call_identity, state="complete", result=value)
                    except (ValueError, TimeoutError) as error:
                        row = dict(
                            identity=call_identity,
                            state="failed",
                            reason=str(error),
                            error_type=type(error).__name__,
                        )
                    path = directory / "calls" / f"{name}.json"
                    immutable(path, row)
                    immutable(
                        directory / "terminations" / path.name,
                        dict(**call_identity, row=binding(path)),
                    )
                    rows[name] = read(path)
                artifacts = assemble(directory, stage, case, parent, frozen, rows)
                if stage == "shape":
                    if any(rows[v]["state"] != "complete" for v in VIEWS):
                        raise ValueError("Required fitted shape view failed")
                    extra["rows"] = [rows[v]["result"] for v in VIEWS]
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
    except discovery.DiscoverySliceExpired as error:
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
    parser.add_argument(
        "command", choices=("freeze-case", "freeze-stage", "run-stage", "read-stage")
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--label")
    parser.add_argument("--membership", type=Path, default=OUTPUT / "membership.json")
    parser.add_argument("--census", type=Path)
    parser.add_argument("--parent-directory", type=Path)
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--slice-id", type=int)
    parser.add_argument("--maximum-seconds", type=float)
    args = parser.parse_args()
    if args.command == "freeze-case":
        if not args.label:
            parser.error("--label required")
        result = freeze_case(
            args.directory, args.label, membership_path=args.membership, census_path=args.census
        )
    elif args.command == "freeze-stage":
        if args.stage is None or args.parent_directory is None:
            parser.error("--stage and --parent-directory required")
        result = freeze_stage(args.directory, args.stage, parent_directory=args.parent_directory)
    elif args.command == "run-stage":
        if args.stage is None or args.slice_id is None:
            parser.error("--stage and --slice-id required")
        result = run_stage(
            args.directory, args.stage, slice_id=args.slice_id, maximum_seconds=args.maximum_seconds
        )
    else:
        result = read_stage(args.directory, args.stage)["terminal"]
    print(
        json.dumps(
            dict(
                command=args.command,
                state=result.get("state", "frozen"),
                label=result.get("label", result.get("policy", {}).get("label")),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
