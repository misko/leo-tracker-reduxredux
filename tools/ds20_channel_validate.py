"""Refine sealed cold discovery and score randomized held windows without truth."""

import argparse
import hashlib
import json
import runpy
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from ds20_channel_corpus import ADAPTER, OUTPUT, ROOT, bounded, digest, write
from ds20_channel_hypotheses import documents, json_value
from ds20_channel_training import LocalPoints, trial_parameters

from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import coordinates
from leo.application.channel_group_discovery import DiscoverySliceExpired
from leo.application.channel_group_held_windows import extract_held_windows
from leo.application.channel_group_holdout import partition_channel_probes, verify_holdout_support
from leo.application.channel_group_refinement import refine_channel_groups
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.regional_position import PositionObservations, RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def paths(
    session,
    early_clock,
    dense=False,
    full_pool=False,
    separate=False,
    point_budget=None,
    calibrated_rematch=False,
    preserve_starts=False,
):
    if point_budget is not None and (point_budget != 300 or not separate):
        raise ValueError("300-point refinement requires separately sealed search hypotheses")
    source = trial_parameters(early_clock, dense)["variant"]
    validation = (
        "cold-random20s-clock-validation-v1" if early_clock else "cold-random20s-validation-v1"
    )
    if dense:
        validation = (
            "cold-random20s-dense-clock-validation-v2"
            if early_clock
            else "cold-random20s-dense-validation-v2"
        )
    if full_pool:
        validation += "-full-pool-v3"
    if separate:
        if not early_clock:
            raise ValueError("Independent source hypotheses require their trained clock layout")
        if full_pool:
            raise ValueError("Separate-search control uses its selected hypothesis union")
        source = "cold-random20s-separate-hypotheses-v1"
        validation = "cold-random20s-separate-validation-v4"
        if point_budget == 300:
            source = "cold-random20s-300point-separate-hypotheses-v2"
            validation = "cold-random20s-300point-separate-validation-v5"
    if calibrated_rematch:
        if not (separate and early_clock and point_budget == 300) or full_pool:
            raise ValueError("Calibrated rematch requires its sealed 300-point early-clock sources")
        source = "calibrated-training-rematch-refit-v2"
        validation = "cold-random20s-calibrated-rematch-validation-v6"
    if preserve_starts:
        if not calibrated_rematch:
            raise ValueError("Preserved start control requires calibrated-rematch source")
        validation = "cold-random20s-rematch-preserved-starts-validation-v7"
    return (
        OUTPUT / "local" / source / session,
        OUTPUT / "local" / validation / session,
    )


def metadata_coverage(source, split):
    endpoints = (
        np.array(
            [min(row[1] for row in split.assignments), max(row[2] for row in split.assignments)]
        )
        / source.sample_rate_hz
    )
    observations = PositionObservations(
        ("metadata-start", "metadata-end"),
        endpoints,
        np.zeros(2),
        np.ones(2) * 1e9,
        np.array([0, 1]),
        np.array([1, 8]),
        np.ones(2),
    )
    nodes = np.arange(np.floor(endpoints[0] / 30) * 30, np.ceil(endpoints[1] / 30) * 30 + 1, 30.0)
    return observations, nodes


def execute(
    session,
    early_clock,
    dense=False,
    full_pool=False,
    separate=False,
    point_budget=None,
    calibrated_rematch=False,
    preserve_starts=False,
):
    begun = time.monotonic()
    cold, directory = paths(
        session,
        early_clock,
        dense,
        full_pool,
        separate,
        point_budget,
        calibrated_rematch,
        preserve_starts,
    )
    if (directory / "terminal.json").exists():
        raise ValueError("Immutable refinement terminal already exists")
    terminal_path = cold / "terminal.json"
    terminal = json.loads(terminal_path.read_bytes())
    cold_protocol = json.loads((cold / "protocol.json").read_bytes())
    extra_starts = []
    if preserve_starts:
        original = OUTPUT / "local/cold-random20s-300point-separate-hypotheses-v2" / session
        old_protocol = json.loads((original / "protocol.json").read_bytes())
        old_terminal = json.loads((original / "terminal.json").read_bytes())
        if (
            digest(original / "protocol.json") != cold_protocol["parent_protocol_sha256"]
            or digest(original / "terminal.json") != cold_protocol["parent_terminal_sha256"]
            or old_terminal["protocol_sha256"] != digest(original / "protocol.json")
            or not old_terminal["result"]["available"]
        ):
            raise ValueError("Original training start provenance differs")
        if any(
            old_protocol[k] != cold_protocol[k]
            for k in (
                "input_sha256",
                "metadata",
                "prepared",
                "seed",
                "held_blocks",
                "partition_sha256",
            )
        ):
            raise ValueError("Original training start evidence differs")
        extra_starts = old_terminal["result"]["selected"]
        if [(r["east_km"], r["north_km"]) for r in extra_starts] != [
            (r["east_km"], r["north_km"]) for r in terminal["result"]["selected"]
        ]:
            raise ValueError("Original and re-associated point locations differ")
        augmented_indices = {
            i for row in terminal["result"]["selected"] for i in row["satellite_indices"]
        }
        if any(not set(row["satellite_indices"]) <= augmented_indices for row in extra_starts):
            raise ValueError("Preserved starts would alter the augmented candidate pool")
    pool_rows = None
    if full_pool:
        pool_rows = []
        for path in sorted((cold / "points").glob("*.json")):
            row = json.loads(path.read_bytes())
            if row["protocol_sha256"] != digest(cold / "protocol.json"):
                raise ValueError("Full-pool training point binding differs")
            pool_rows.append(row["result"])
    if (
        terminal["protocol_sha256"] != digest(cold / "protocol.json")
        or not terminal["result"]["available"]
    ):
        raise ValueError("Three sealed available training-only discovery starts required")
    membership = json.loads((OUTPUT / "membership.json").read_bytes())
    member = next(row for row in membership["members"] if row["session_id"] == session)
    if member["role"] != "development":
        raise ValueError("Development refinement cannot consume validation recordings")
    input_path = Path(member["input"]["path"])
    if digest(input_path) != cold_protocol["input_sha256"]:
        raise ValueError("Bound original input differs")
    source = runpy.run_path(str(ADAPTER))["load_tracking_input"](
        json.loads(input_path.read_bytes())
    )
    with bounded(60):
        split = partition_channel_probes(source)
        verify_holdout_support(source, split)
        if (
            list(split.held_blocks) != cold_protocol["held_blocks"]
            or split.seed != cold_protocol["seed"]
        ):
            raise ValueError("Randomized partition differs from cold discovery")
        assignment_sha = (
            "sha256:" + hashlib.sha256(json.dumps(split.assignments).encode()).hexdigest()
        )
        if assignment_sha != cold_protocol["partition_sha256"]:
            raise ValueError("Whole-probe assignments differ from sealed discovery")
        prepared, held = {}, {}
        for view, channels in membership["views"].items():
            if view not in cold_protocol["prepared"]:
                continue
            train_source = replace(
                split.training,
                probes=tuple(p for p in split.training.probes if p.channel in channels),
            )
            prepared[view] = prepare_position_windows(train_source)
            if prepared[view].evidence_sha256 != cold_protocol["prepared"][view]:
                raise ValueError("Training Hough/candidate evidence differs")
            held_source = replace(
                split.held, probes=tuple(p for p in split.held.probes if p.channel in channels)
            )
            held[view] = extract_held_windows(held_source)
    prior = RegionalPrior(**cold_protocol["metadata"]["prior"])
    coverage, nodes = metadata_coverage(source, split)
    protocol = dict(
        policy="cold-randomized-channel-refinement-v1",
        session_id=session,
        cold_terminal_sha256=digest(terminal_path),
        cold_protocol_sha256=digest(cold / "protocol.json"),
        input_sha256=digest(input_path),
        metadata=cold_protocol["metadata"],
        seed=split.seed,
        held_blocks=list(split.held_blocks),
        prepared=cold_protocol["prepared"],
        clock_nodes_s=nodes.tolist(),
        clock_prior_scale=4,
        models=["constant", "differential-clock"],
        arms=["fitted-c", "zero-c"],
        starts=3 + len(extra_starts),
        seconds_per_fit=45,
        iterations=600,
        maximum_slices=3,
        slice_seconds=500,
        model_selection="none; report matched model hypotheses separately",
        candidate_pool=(
            "Augmented union unchanged; original starts add no candidates"
            if preserve_starts
            else "Union of all sealed training proposals"
            if full_pool
            else "Union of three selected training starts"
        ),
        timing_initializer="Current point then nearest stationary training point"
        if full_pool
        else "Current point then declared selected-start order",
        reference_usage="none",
        held_parameters_fitted=0,
        c_ablation="Conditional on common fitted-c training discovery and starts",
        source_files={
            str(path): digest(path)
            for path in (
                Path(__file__),
                ROOT / "tools/ds20_channel_training.py",
                ADAPTER,
                ROOT / "src/leo/application/channel_group_refinement.py",
                ROOT / "src/leo/application/channel_group_held_windows.py",
                ROOT / "src/leo/analysis/frozen_position_prediction.py",
                ROOT / "src/leo/analysis/frozen_group_calibration.py",
                ROOT / "src/leo/analysis/channel_group_calibration.py",
            )
        },
    )
    protocol_path = directory / "protocol.json"
    if protocol_path.exists() and json.loads(protocol_path.read_bytes()) != protocol:
        raise ValueError("Frozen refinement protocol differs")
    write(protocol_path, protocol)
    binding = digest(protocol_path)
    for path, sha in protocol["source_files"].items():
        snapshot = directory / "source-snapshot" / Path(path).name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not snapshot.exists():
            snapshot.write_bytes(Path(path).read_bytes())
        if digest(snapshot) != sha:
            raise ValueError("Refinement snapshot differs")
    ledger_path = directory / "slices.json"
    ledger = json.loads(ledger_path.read_bytes()) if ledger_path.exists() else []
    if len(ledger) >= 3:
        raise ValueError("Three-slice refinement budget exhausted")
    ledger.append(dict(index=len(ledger), state="started", configured_seconds=500))
    write(ledger_path, ledger)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = next(
        row
        for row in archive.list_snapshots()
        if row.digest == cold_protocol["metadata"]["snapshot_sha256"]
    )
    catalogue = parse_element_sets(archive.read(snapshot))
    indices = [
        i
        for i, name in enumerate(catalogue.names)
        if name.upper().startswith("STARLINK") and "DEB" not in name.upper()
    ]
    propagated, _ = build_regional_bank(
        catalogue, indices, prepared["all"].start_utc_ns, coverage, prior, maximum_seconds=180
    )
    # Only extend geometric time coverage. Preserve the cold bank's candidate
    # identity/order so every index in the sealed training result remains valid.
    with np.load(cold / "bank.npz") as values:
        numbers = values["numbers"].copy()
    receipt = json.loads((cold / "bank.json").read_bytes())
    if receipt["bank_sha256"] != digest(cold / "bank.npz") or receipt["protocol_sha256"] != digest(
        cold / "protocol.json"
    ):
        raise ValueError("Bound cold candidate bank differs")
    lookup = {int(number): i for i, number in enumerate(propagated.numbers)}
    bank = propagated.select([lookup[int(number)] for number in numbers])
    try:
        result = refine_channel_groups(
            terminal["result"],
            prepared,
            held,
            bank,
            prior,
            nodes,
            LocalPoints(directory / "fits", binding),
            early_clock=early_clock,
            maximum_seconds=max(1.0, 500 - (time.monotonic() - begun)),
            training_rows=pool_rows,
            extra_starts=extra_starts,
        )
    except DiscoverySliceExpired as error:
        ledger[-1].update(
            state="slice-expired", reason=str(error), elapsed_s=time.monotonic() - begun
        )
        write(ledger_path, ledger)
        if len(ledger) == 3:
            write(
                directory / "terminal.json",
                dict(
                    protocol_sha256=binding,
                    result=dict(available=False, stop_reason="three-slice-budget-exhausted"),
                    slices=ledger,
                ),
            )
        print(json.dumps(ledger[-1]), flush=True)
        return
    if any(digest(Path(path)) != sha for path, sha in protocol["source_files"].items()):
        raise ValueError("Refinement source changed during inference")
    ledger[-1].update(state="complete", elapsed_s=time.monotonic() - begun)
    write(ledger_path, ledger)
    write(
        directory / "terminal.json",
        json_value(dict(protocol_sha256=binding, result=result, slices=ledger)),
    )
    print(json.dumps(dict(models=list(result["results"]), state="sealed")), flush=True)


def evaluate(
    session,
    early_clock,
    dense=False,
    full_pool=False,
    separate=False,
    point_budget=None,
    calibrated_rematch=False,
    preserve_starts=False,
):
    _, directory = paths(
        session,
        early_clock,
        dense,
        full_pool,
        separate,
        point_budget,
        calibrated_rematch,
        preserve_starts,
    )
    terminal_path = directory / "terminal.json"
    terminal = json.loads(terminal_path.read_bytes())
    protocol = json.loads((directory / "protocol.json").read_bytes())
    if terminal["protocol_sha256"] != digest(directory / "protocol.json"):
        raise ValueError("Inference terminal/protocol differs")
    if "results" not in terminal["result"]:
        raise ValueError("No completed refinement result to evaluate")
    # This is the only stage that accesses reference coordinates, after seal.
    docs, _ = documents(session)
    reference = docs["all"]["reference_latitude_deg"], docs["all"]["reference_longitude_deg"]
    prior = RegionalPrior(**protocol["metadata"]["prior"])
    result = {}
    for model, views in terminal["result"]["results"].items():
        result[model] = {}
        for view, row in views.items():
            result[model][view] = {}
            for arm, selection in row["selected"].items():
                if "fit" not in selection:
                    result[model][view][arm] = selection
                    continue
                fit = selection["fit"]
                point = coordinates(prior, fit["vector"][:2])
                lat, lon, a, b = np.radians([*point, *reference])
                h = (
                    np.sin((lat - a) / 2) ** 2
                    + np.cos(lat) * np.cos(a) * np.sin((lon - b) / 2) ** 2
                )
                result[model][view][arm] = dict(
                    error_m=float(2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))),
                    training_rms_hz=fit["posterior_rms_hz"],
                    held_prediction=selection["held_prediction"],
                )
    write(
        directory / "evaluation.json",
        dict(
            terminal_sha256=digest(terminal_path),
            summary=result,
            reference_usage="Only after sealed inference",
            scope=(
                "Randomized exposed-DS20 development falsification; "
                "no independent recording validation"
            ),
        ),
    )
    print(
        json.dumps(
            {
                model: {
                    view: {arm: row.get("error_m", row.get("state")) for arm, row in arms.items()}
                    for view, arms in views.items()
                }
                for model, views in result.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("execute", "evaluate"))
    parser.add_argument("session_id")
    parser.add_argument("--early-clock", action="store_true")
    parser.add_argument("--dense", action="store_true")
    parser.add_argument("--full-pool", action="store_true")
    parser.add_argument("--separate-searches", action="store_true")
    parser.add_argument("--point-budget", type=int, choices=(300,))
    parser.add_argument("--calibrated-rematch", action="store_true")
    parser.add_argument("--preserve-starts", action="store_true")
    args = parser.parse_args()
    (execute if args.command == "execute" else evaluate)(
        args.session_id,
        args.early_clock,
        args.dense,
        args.full_pool,
        args.separate_searches,
        args.point_budget,
        args.calibrated_rematch,
        args.preserve_starts,
    )
