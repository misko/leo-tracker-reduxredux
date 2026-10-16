"""Shared, reference-free DS21 inventory, preparation and cold discovery ports."""

import argparse
import json
import random
import runpy
import time
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from ds20_channel_corpus import ADAPTER, bounded, digest, write
from ds20_channel_hypotheses import json_value
from ds20_channel_training import LocalPoints
from ds20_channel_validate import metadata_coverage

from leo.analysis.regional_position_bank import build_regional_bank
from leo.application.channel_group_discovery import DiscoverySliceExpired, discover_channel_groups
from leo.application.channel_group_held_windows import extract_held_windows
from leo.application.channel_group_holdout import partition_channel_probes, verify_holdout_support
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

AUTHORITY = Path(
    "/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_12_ds21_post_ds20/local"
)
OUTPUT = Path("/home/mouse9911/gits/leo-ds21-three-models/reports/2026_10_13_ds21_three_models")
VIEWS = {"all": list(range(1, 9)), "low": list(range(1, 5)), "high": list(range(5, 9))}
SEED = 20261013


def assignments(members, seed=SEED):
    """Randomize whole UTC-hour acquisition groups, never individual windows.

    An hour group conservatively keeps nearby fast/adaptive recordings together.
    This does not assert independent hardware or satellite errors between hours.
    Duplicate physical acquisitions must already be deduplicated by the authority.
    """
    groups = sorted({m["captured_utc_ns"] // 3_600_000_000_000 for m in members})
    if len(groups) < 3:
        raise ValueError("At least three acquisition groups required")
    shuffled = list(groups)
    random.Random(seed).shuffle(shuffled)
    evaluation = set(shuffled[: max(1, round(len(groups) / 3))])
    return {
        m["dataset_label"]: {
            "group": m["captured_utc_ns"] // 3_600_000_000_000,
            "role": "evaluation"
            if m["captured_utc_ns"] // 3_600_000_000_000 in evaluation
            else "development",
        }
        for m in members
    }


def immutable(path, value):
    value = json.loads(json.dumps(json_value(value), allow_nan=False))
    if path.exists():
        if json.loads(path.read_bytes()) != value:
            raise ValueError(f"Immutable research receipt differs: {path}")
    else:
        write(path, value)


def freeze(authority=AUTHORITY, output=OUTPUT):
    path = authority / "manifest.json"
    seal = json.loads((authority / "seal.json").read_bytes())
    if digest(path) != seal["files"]["manifest.json"]:
        raise ValueError("DS21 manifest seal differs")
    manifest = json.loads(path.read_bytes())
    if manifest["dataset_id"] != "DS21":
        raise ValueError("DS21 authority required")
    roles = assignments(manifest["members"])
    members = []
    for row in manifest["members"]:
        inputs = row["tracking_inputs"]
        receipt = None
        if inputs:
            source = inputs[0]
            relative = source["snapshot"]
            if seal["files"].get(relative) != source["sha256"]:
                raise ValueError("Tracking snapshot not bound by authority seal")
            receipt = dict(path=str(authority / relative), sha256=source["sha256"])
        members.append(
            dict(
                label=row["dataset_label"],
                session_id=row["session_id"],
                recording_id=row["recording_id"],
                raw_identity=row["raw_recording"]["identity_sha256"],
                captured_utc_ns=row["captured_utc_ns"],
                channels=row["observed_channels"],
                eight_channel=row["observed_channels"] == VIEWS["all"],
                input=receipt,
                **roles[row["dataset_label"]],
            )
        )
    value = dict(
        dataset="DS21",
        authority=str(path),
        authority_sha256=digest(path),
        authority_seal_sha256=digest(authority / "seal.json"),
        adapter=str(ADAPTER),
        adapter_sha256=digest(ADAPTER),
        seed=SEED,
        grouping="whole UTC-hour acquisition groups; randomized group roles",
        split_scope="Development errors may inform iteration; evaluation errors remain sealed",
        acceptance="All eight-channel evaluation members below 1 km; failures count as misses",
        eligibility="Acquired CH1-8; no quality, preparation or inference-success exclusion",
        views=VIEWS,
        prior=asdict(RegionalPrior()),
        members=members,
    )
    immutable(output / "membership.json", value)
    return value


def load_source(member, membership):
    if member["input"] is None:
        raise ValueError("No sealed tracking input; raw re-analysis required")
    receipt = member["input"]
    path = Path(receipt["path"])
    if digest(path) != receipt["sha256"] or digest(ADAPTER) != membership["adapter_sha256"]:
        raise ValueError("Pinned tracking input or loader differs")
    # Native session identities can differ from raw-acquisition labels. The
    # authority binds them by raw content, not by a guessed session-name equality.
    return runpy.run_path(str(ADAPTER))["load_tracking_input"](json.loads(path.read_bytes()))


def prepare_case(member, membership):
    source = load_source(member, membership)
    split = partition_channel_probes(source)
    verify_holdout_support(source, split)
    prepared, held, failures = {}, {}, {}
    for view, channels in VIEWS.items():
        train = replace(
            split.training,
            probes=tuple(p for p in split.training.probes if p.channel in channels),
        )
        validation = replace(
            split.held,
            probes=tuple(p for p in split.held.probes if p.channel in channels),
        )
        try:
            prepared[view] = prepare_position_windows(train)
        except ValueError as error:
            failures[view] = str(error)
        try:
            held[view] = extract_held_windows(validation)
        except ValueError as error:
            failures[view + "_held"] = str(error)
    envelope, nodes = metadata_coverage(source, split)
    return dict(
        source=source,
        split=split,
        prepared=prepared,
        held=held,
        failures=failures,
        prior=RegionalPrior(**membership["prior"]),
        nodes=nodes,
        envelope=envelope,
    )


def census(membership, *, maximum_cases=8, output=OUTPUT):
    done = 0
    for member in membership["members"]:
        path = output / "local/census" / (member["label"] + ".json")
        if path.exists():
            continue
        if not member["eight_channel"]:
            row = dict(label=member["label"], state="four-channel-secondary-benchmark")
        elif done >= maximum_cases:
            continue
        else:
            done += 1
            try:
                with bounded(60):
                    case = prepare_case(member, membership)
                row = dict(
                    label=member["label"],
                    state="prepared",
                    role=member["role"],
                    native_session_id=case["source"].session_id,
                    sample_rate_hz=case["source"].sample_rate_hz,
                    views={
                        k: dict(
                            windows=len(v.observations.window_ids),
                            tracks=len(v.bootstrap_tracks),
                            evidence_sha256=v.evidence_sha256,
                        )
                        for k, v in case["prepared"].items()
                    },
                    failures=case["failures"],
                    split_seed=case["split"].seed,
                    held_blocks=case["split"].held_blocks,
                )
            except (ValueError, OSError, TimeoutError) as error:
                row = dict(label=member["label"], state="unavailable", reason=str(error))
        immutable(path, dict(membership_sha256=digest(output / "membership.json"), **row))
        print(json.dumps(row), flush=True)
    rows = [json.loads(p.read_bytes()) for p in sorted((output / "local/census").glob("*.json"))]
    write(
        output / "coverage.json",
        dict(total=len(membership["members"]), reviewed=len(rows), rows=rows),
    )


def discover(label, *, output=OUTPUT):
    membership = json.loads((output / "membership.json").read_bytes())
    member = next(m for m in membership["members"] if m["label"] == label)
    if member["role"] != "development":
        raise ValueError("Evaluation discovery requires a frozen model release")
    directory = output / "local/discovery-v2" / label
    if (directory / "terminal.json").exists():
        return json.loads((directory / "terminal.json").read_bytes())
    started = time.monotonic()
    case = prepare_case(member, membership)
    if "all" not in case["prepared"]:
        raise ValueError("All-channel training preparation unavailable")
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(case["prepared"]["all"].start_utc_ns)
    protocol = dict(
        membership_sha256=digest(output / "membership.json"),
        label=label,
        input_sha256=member["input"]["sha256"],
        snapshot_sha256=snapshot.digest,
        snapshot_collected_utc_ns=snapshot.collected_utc_ns,
        prepared={k: v.evidence_sha256 for k, v in case["prepared"].items()},
        seed=case["split"].seed,
        held_blocks=case["split"].held_blocks,
        prior=asdict(case["prior"]),
        points=100,
        levels_km=[100.0, 50.0, 25.0, 12.5],
        c_scope="Shared fitted-c discovery; downstream c ablations use common bank/starts",
        reference_usage="none",
        source_sha256=digest(Path(__file__)),
    )
    pp = directory / "protocol.json"
    immutable(pp, protocol)
    bank_path = directory / "bank.npz"
    if (directory / "bank.json").exists():
        receipt = json.loads((directory / "bank.json").read_bytes())
        if receipt["sha256"] != digest(bank_path):
            raise ValueError("Shared orbit bank differs")
        with np.load(bank_path) as arrays:
            bank = PositionOrbitBank(
                *(arrays[k] for k in ("numbers", "nodes_s", "position_km", "velocity_km_s"))
            )
    else:
        catalogue = parse_element_sets(archive.read(snapshot))
        indices = [
            i
            for i, name in enumerate(catalogue.names)
            if name.upper().startswith("STARLINK") and "DEB" not in name.upper()
        ]
        bank, receipt = build_regional_bank(
            catalogue,
            indices,
            case["prepared"]["all"].start_utc_ns,
            case["envelope"],
            case["prior"],
            maximum_seconds=180,
        )
        np.savez(
            bank_path,
            **{k: getattr(bank, k) for k in ("numbers", "nodes_s", "position_km", "velocity_km_s")},
        )
        immutable(directory / "bank.json", dict(sha256=digest(bank_path), build=asdict(receipt)))
    try:
        result = discover_channel_groups(
            case["prepared"],
            bank,
            case["prior"],
            LocalPoints(directory / "points", digest(pp)),
            maximum_seconds=max(1.0, 500 - (time.monotonic() - started)),
            points=100,
            clock_nodes=case["nodes"],
        )
    except DiscoverySliceExpired as error:
        print(json.dumps(dict(label=label, state="checkpointed", next=str(error))), flush=True)
        return None
    terminal = dict(protocol_sha256=digest(pp), result=json_value(result))
    immutable(directory / "terminal.json", terminal)
    print(
        json.dumps(dict(label=label, state="complete", available=result["available"])), flush=True
    )
    return terminal


def load_case(label, *, output=OUTPUT):
    """Shared in-memory port consumed by all three model-specific runners."""
    membership = json.loads((output / "membership.json").read_bytes())
    member = next(m for m in membership["members"] if m["label"] == label)
    if member["role"] != "development":
        raise ValueError("Evaluation cases require a frozen model release")
    directory = output / "local/discovery-v2" / label
    protocol = json.loads((directory / "protocol.json").read_bytes())
    terminal = json.loads((directory / "terminal.json").read_bytes())
    if terminal["protocol_sha256"] != digest(directory / "protocol.json"):
        raise ValueError("Shared discovery binding differs")
    if protocol["membership_sha256"] != digest(output / "membership.json"):
        raise ValueError("Shared discovery membership differs")
    if not terminal["result"]["available"]:
        raise ValueError("Shared discovery did not produce three starts")
    case = prepare_case(member, membership)
    if protocol["prepared"] != {k: v.evidence_sha256 for k, v in case["prepared"].items()}:
        raise ValueError("Rebuilt training evidence differs")
    receipt = json.loads((directory / "bank.json").read_bytes())
    if receipt["sha256"] != digest(directory / "bank.npz"):
        raise ValueError("Shared orbit bank changed")
    with np.load(directory / "bank.npz") as arrays:
        full_bank = PositionOrbitBank(
            *(arrays[k] for k in ("numbers", "nodes_s", "position_km", "velocity_km_s"))
        )
    rows = terminal["result"]["selected"]
    indices = sorted(
        {i for row in rows for i in row["satellite_indices"]}, key=lambda i: full_bank.numbers[i]
    )
    case.update(
        member=member,
        full_bank=full_bank,
        bank=full_bank.select(indices),
        discovery=terminal["result"],
        directory=directory,
        protocol_sha256=digest(directory / "protocol.json"),
    )
    return case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "census", "discover"))
    parser.add_argument("--label")
    parser.add_argument("--maximum-cases", type=int, default=8)
    args = parser.parse_args()
    if args.command == "freeze":
        value = freeze()
        roles = Counter(
            m["role"] + ("-eight" if m["eight_channel"] else "-four") for m in value["members"]
        )
        print(json.dumps(dict(members=len(value["members"]), roles=dict(roles))))
    elif args.command == "census":
        census(
            json.loads((OUTPUT / "membership.json").read_bytes()), maximum_cases=args.maximum_cases
        )
    else:
        if not args.label:
            parser.error("discover requires --label")
        discover(args.label)


if __name__ == "__main__":
    main()
