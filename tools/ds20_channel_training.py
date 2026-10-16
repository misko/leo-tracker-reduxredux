"""Bounded cold training-only discovery; no fitted donor or reference input."""

import argparse
import hashlib
import json
import runpy
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from ds20_channel_corpus import ADAPTER, OUTPUT, ROOT, bounded, digest, write
from ds20_channel_hypotheses import documents, json_value

from leo.analysis.regional_position_bank import build_regional_bank
from leo.application.channel_group_discovery import DiscoverySliceExpired, discover_channel_groups
from leo.application.channel_group_holdout import partition_channel_probes, verify_holdout_support
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def fixed_metadata(docs):
    """Discard all learned states and reference fields at the metadata boundary."""
    prior = docs["all"]["configuration"]["prior"]
    snapshot = docs["all"]["diagnostics"]["snapshot_sha256"]
    if any(
        doc["configuration"]["prior"] != prior or doc["diagnostics"]["snapshot_sha256"] != snapshot
        for doc in docs.values()
    ):
        raise ValueError("Original channel controls have different fixed prior/TLE metadata")
    return dict(prior=prior, snapshot_sha256=snapshot)


class LocalPoints:
    def __init__(self, root, binding, parents=()):
        self.root, self.binding = root, binding
        self.parents = parents

    def path(self, key):
        return self.root / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def get(self, key):
        path = self.path(key)
        if not path.exists():
            for parent_root, parent_binding in self.parents:
                parent = parent_root / path.name
                if not parent.exists():
                    continue
                value = json.loads(parent.read_bytes())
                if value["protocol_sha256"] != parent_binding or value["key"] != key:
                    raise ValueError("Reused training point binding differs")
                self.put(key, value["result"])
                copied = json.loads(path.read_bytes())
                copied["reused_parent_receipt_sha256"] = digest(parent)
                write(path, copied)
                return value["result"]
            return None
        value = json.loads(path.read_bytes())
        if value["protocol_sha256"] != self.binding or value["key"] != key:
            raise ValueError("Discovery point belongs to a different bound trial")
        return value["result"]

    def put(self, key, result):
        if self.path(key).exists():
            raise ValueError("An immutable point receipt cannot be overwritten")
        write(
            self.path(key), dict(protocol_sha256=self.binding, key=key, result=json_value(result))
        )


def trial_parameters(early_clock, dense, point_budget=None, priority_view="all"):
    if priority_view not in ("all", "low", "high"):
        raise ValueError("Unknown training search priority")
    if point_budget is not None and point_budget != 300:
        raise ValueError("Only the measured 300-point follow-up is supported")
    if (priority_view != "all" or point_budget is not None) and not (early_clock and dense):
        raise ValueError("Independent bounded control requires the dense early-clock policy")
    variant = (
        (
            "cold-random20s-dense-clock-discovery-v3"
            if early_clock
            else "cold-random20s-dense-discovery-v3"
        )
        if dense
        else ("cold-random20s-clock-discovery-v2" if early_clock else "cold-random20s-discovery-v1")
    )
    if priority_view != "all":
        variant = f"cold-random20s-independent-{priority_view}-discovery-v4"
    if point_budget is not None:
        variant = f"cold-random20s-300point-{priority_view}-discovery-v5"
    return dict(
        variant=variant,
        policy=variant.replace("random20s", "channel-group"),
        points=point_budget if point_budget is not None else (400 if dense else 100),
        levels=(40.0, 20.0, 10.0, 5.0) if dense else (100.0, 50.0, 25.0, 12.5),
    )


def verify_point_parent(root, numerical):
    """A failed search can supply complete points, never a successful terminal.

    Search budget/priority and the driver may differ. The point evaluator,
    training evidence, orbit prior, partition and numerical limits must match.
    """
    path = root / "protocol.json"
    protocol = json.loads(path.read_bytes())
    terminal = json.loads((root / "terminal.json").read_bytes())
    if terminal["protocol_sha256"] != digest(path):
        raise ValueError("Training point parent terminal binding differs")
    for field, value in numerical.items():
        if field == "source_files":
            if any(protocol[field].get(name) != sha for name, sha in value.items()):
                raise ValueError("Training point parent evaluator source differs")
        elif protocol[field] != value:
            raise ValueError(f"Training point parent numerical policy differs: {field}")
    receipt = json.loads((root / "bank.json").read_bytes())
    if receipt["protocol_sha256"] != digest(path) or receipt["bank_sha256"] != digest(
        root / "bank.npz"
    ):
        raise ValueError("Training point parent bank binding differs")
    return (root / "points", digest(path))


def execute(session, *, early_clock=False, dense=False, priority_view="all", point_budget=None):
    begun = time.monotonic()
    membership = json.loads((OUTPUT / "membership.json").read_bytes())
    member = next(row for row in membership["members"] if row["session_id"] == session)
    if member["role"] != "development":
        raise ValueError("Cold discovery development trial cannot consume validation recordings")
    trial = trial_parameters(early_clock, dense, point_budget, priority_view)
    directory = OUTPUT / "local" / trial["variant"] / session
    if (directory / "terminal.json").exists():
        raise ValueError("Immutable terminal already exists")
    input_path = Path(member["input"]["path"])
    if digest(input_path) != member["input"]["sha256"]:
        raise ValueError("Original DS20 input differs")
    source = runpy.run_path(str(ADAPTER))["load_tracking_input"](
        json.loads(input_path.read_bytes())
    )
    with bounded(60):
        split = partition_channel_probes(source)
        containment = verify_holdout_support(source, split)
        prepared, failures = {}, {}
        for view, channels in membership["views"].items():
            training = replace(
                split.training,
                probes=tuple(p for p in split.training.probes if p.channel in channels),
            )
            try:
                prepared[view] = prepare_position_windows(training)
            except ValueError as error:
                failures[view] = f"{type(error).__name__}: {error}"
    docs, origins = documents(session)
    metadata = fixed_metadata(docs)
    prior = RegionalPrior(**metadata["prior"])
    parents = []
    parent_bindings = {}
    if priority_view != "all" and point_budget is None:
        parent_root = OUTPUT / "local/cold-random20s-dense-clock-discovery-v3" / session
        parent_path = parent_root / "protocol.json"
        parent_protocol = json.loads(parent_path.read_bytes())
        parent_terminal = json.loads((parent_root / "terminal.json").read_bytes())
        if (
            parent_terminal["protocol_sha256"] != digest(parent_path)
            or parent_protocol["input_sha256"] != digest(input_path)
            or parent_protocol["metadata"] != metadata
            or parent_protocol["prepared"]
            != {name: row.evidence_sha256 for name, row in prepared.items()}
        ):
            raise ValueError("Independent search parent numerical evidence differs")
        parents = [(parent_root / "points", digest(parent_path))]
        parent_bindings = {
            str(parent_path): digest(parent_path),
            str(parent_root / "terminal.json"): digest(parent_root / "terminal.json"),
        }
    clock_nodes = (
        np.arange(
            np.floor(min(row[1] for row in split.assignments) / source.sample_rate_hz / 30) * 30,
            np.ceil(max(row[2] for row in split.assignments) / source.sample_rate_hz / 30) * 30 + 1,
            30.0,
        )
        if early_clock
        else None
    )
    protocol = dict(
        policy=trial["policy"],
        session_id=session,
        membership_sha256=digest(OUTPUT / "membership.json"),
        input_sha256=digest(input_path),
        metadata=metadata,
        metadata_sources=origins,
        seed=split.seed,
        block_seconds=split.block_seconds,
        held_blocks=list(split.held_blocks),
        partition_sha256="sha256:"
        + hashlib.sha256(json.dumps(split.assignments).encode()).hexdigest(),
        containment=containment,
        prepared={view: row.evidence_sha256 for view, row in prepared.items()},
        preparation_failures=failures,
        maximum_slices=3,
        slice_seconds=500,
        point_budget=trial["points"],
        levels_km=list(trial["levels"]),
        seconds_per_bootstrap=5,
        seconds_per_fit=5,
        iterations=200,
        common_clock_nodes_s=clock_nodes.tolist() if early_clock else None,
        clock_prior_scale=4 if early_clock else None,
        priority_view=priority_view,
        reused_training_point_parents=parent_bindings,
        views=list(prepared),
        candidate_policy=(
            "Union of independently rebuilt training low/high/all bootstrap proposals "
            "at each common point"
        ),
        discovery_c_arm=(
            "fitted-c; subsequent c=0 comparison conditional on this training discovery"
        ),
        reference_usage="none",
        full_data_learned_state_usage="none",
        source_files={
            str(path): digest(path)
            for path in (
                Path(__file__),
                ADAPTER,
                ROOT / "tools/ds20_channel_hypotheses.py",
                ROOT / "src/leo/application/channel_group_discovery.py",
                ROOT / "src/leo/application/channel_group_holdout.py",
                ROOT / "src/leo/analysis/channel_group_seeds.py",
                ROOT / "src/leo/analysis/channel_group_calibration.py",
                ROOT / "src/leo/analysis/hard60_joint_clock.py",
            )
        },
    )
    if point_budget is not None:
        variants = ["cold-random20s-dense-clock-discovery-v3"]
        if priority_view != "all":
            variants.insert(0, "cold-random20s-300point-all-discovery-v5")
        numerical = {
            key: protocol[key]
            for key in (
                "input_sha256",
                "metadata",
                "prepared",
                "held_blocks",
                "partition_sha256",
                "seed",
                "levels_km",
                "seconds_per_bootstrap",
                "seconds_per_fit",
                "iterations",
                "common_clock_nodes_s",
                "clock_prior_scale",
                "candidate_policy",
                "discovery_c_arm",
            )
        }
        numerical["source_files"] = {
            name: sha
            for name, sha in protocol["source_files"].items()
            if name != str(Path(__file__))
        }
        for variant in variants:
            parent_root = OUTPUT / "local" / variant / session
            if not (parent_root / "terminal.json").exists():
                continue
            parents.append(verify_point_parent(parent_root, numerical))
            for name in ("protocol.json", "terminal.json", "bank.json"):
                parent_bindings[str(parent_root / name)] = digest(parent_root / name)
    protocol_path = directory / "protocol.json"
    if protocol_path.exists() and json.loads(protocol_path.read_bytes()) != protocol:
        raise ValueError("Frozen cold discovery protocol changed")
    write(protocol_path, protocol)
    binding = digest(protocol_path)
    snapshot_root = directory / "source-snapshot"
    for path, sha in protocol["source_files"].items():
        snapshot = snapshot_root / Path(path).name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not snapshot.exists():
            snapshot.write_bytes(Path(path).read_bytes())
        if digest(snapshot) != sha:
            raise ValueError("Cold discovery source snapshot differs")
    ledger_path = directory / "slices.json"
    ledger = json.loads(ledger_path.read_bytes()) if ledger_path.exists() else []
    if len(ledger) >= 3:
        raise ValueError("Three-slice development budget exhausted")
    ledger.append(dict(index=len(ledger), state="started", configured_seconds=500))
    write(ledger_path, ledger)
    bank_path, bank_receipt = directory / "bank.npz", directory / "bank.json"
    if bank_receipt.exists():
        receipt = json.loads(bank_receipt.read_bytes())
        if receipt["protocol_sha256"] != binding or receipt["bank_sha256"] != digest(bank_path):
            raise ValueError("Bound training bank differs")
        with np.load(bank_path) as values:
            bank = PositionOrbitBank(
                *(values[key] for key in ("numbers", "nodes_s", "position_km", "velocity_km_s"))
            )
    else:
        archive = TleArchiveReader(Path("/var/lib/leo/tle"))
        snapshot = next(
            row for row in archive.list_snapshots() if row.digest == metadata["snapshot_sha256"]
        )
        if snapshot.collected_utc_ns > prepared["all"].start_utc_ns:
            raise ValueError("Future TLE snapshot forbidden")
        catalogue = parse_element_sets(archive.read(snapshot))
        indices = [
            i
            for i, name in enumerate(catalogue.names)
            if name.upper().startswith("STARLINK") and "DEB" not in name.upper()
        ]
        bank, receipt = build_regional_bank(
            catalogue,
            indices,
            prepared["all"].start_utc_ns,
            prepared["all"].observations,
            prior,
            maximum_seconds=180,
        )
        np.savez(
            bank_path,
            numbers=bank.numbers,
            nodes_s=bank.nodes_s,
            position_km=bank.position_km,
            velocity_km_s=bank.velocity_km_s,
        )
        write(
            bank_receipt,
            dict(protocol_sha256=binding, bank_sha256=digest(bank_path), receipt=asdict(receipt)),
        )
    try:
        for parent_points, _ in parents:
            with np.load(parent_points.parent / "bank.npz") as old:
                if not all(
                    np.array_equal(old[key], getattr(bank, key))
                    for key in ("numbers", "nodes_s", "position_km", "velocity_km_s")
                ):
                    raise ValueError("Reused training point orbit bank arrays differ")
        result = discover_channel_groups(
            prepared,
            bank,
            prior,
            LocalPoints(directory / "points", binding, parents),
            maximum_seconds=max(1.0, 500 - (time.monotonic() - begun)),
            points=trial["points"],
            clock_nodes=clock_nodes,
            levels_km=trial["levels"],
            priority_view=priority_view,
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
                    result=dict(
                        available=False,
                        stop_reason="three-slice-budget-exhausted",
                        completed_point_receipts=len(list((directory / "points").glob("*.json"))),
                    ),
                    reference_usage="none",
                    full_data_learned_state_usage="none",
                    slices=ledger,
                ),
            )
        print(json.dumps(ledger[-1]), flush=True)
        return
    if any(digest(Path(path)) != sha for path, sha in protocol["source_files"].items()):
        raise ValueError("Cold discovery source changed during slice")
    ledger[-1].update(state="complete", elapsed_s=time.monotonic() - begun)
    write(ledger_path, ledger)
    write(
        directory / "terminal.json",
        json_value(
            dict(
                protocol_sha256=binding,
                result=result,
                reference_usage="none",
                full_data_learned_state_usage="none",
                slices=ledger,
            )
        ),
    )
    print(json.dumps(dict(points=result["points"], available=result["available"])), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("--early-clock", action="store_true")
    parser.add_argument("--dense", action="store_true")
    parser.add_argument("--priority-view", choices=("all", "low", "high"), default="all")
    parser.add_argument("--point-budget", type=int, choices=(300,))
    args = parser.parse_args()
    execute(
        args.session_id,
        early_clock=args.early_clock,
        dense=args.dense,
        priority_view=args.priority_view,
        point_budget=args.point_budget,
    )
