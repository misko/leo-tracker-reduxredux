"""Sealed six-source training proposal pool on the fixed Model B-v3 bank."""

import argparse
import json
from pathlib import Path

from leo.analysis.research.doppler_shape_shared_proposals import (
    PROPOSAL_IDS,
    encode_initial_physical_seed,
    ordered_seed_entries,
)
from leo.application.channel_group_refinement import objective


def read_bound(path, expected, digest):
    if digest(path) != expected:
        raise ValueError(f"Shared proposal file binding differs: {path.name}")
    return json.loads(path.read_bytes())


def build(label):
    import ds21_common as shared
    from ds21_common import OUTPUT, digest, immutable, load_case

    case = load_case(label)
    b3 = OUTPUT / "local/model-b-shape-fresh-absolute-hybrid-v3" / label
    cold = OUTPUT / "local/cold-start-control-v1" / label
    pool = json.loads((b3 / "candidate-pool.json").read_bytes())
    b3_terminal = json.loads((b3 / "terminal.json").read_bytes())
    read_bound(b3 / "protocol.json", b3_terminal["protocol_sha256"], digest)
    cold_terminal = json.loads((cold / "terminal.json").read_bytes())
    cold_protocol = read_bound(cold / "protocol.json", cold_terminal["protocol_sha256"], digest)
    if b3_terminal.get("state") != "complete" or cold_terminal.get("state") != "complete":
        raise ValueError("Sealed shape and cold-control parents required")
    if cold_protocol["parent_v3_terminal_sha256"] != digest(b3 / "terminal.json"):
        raise ValueError("Cold seeds and Model B-v3 terminal differ")
    if cold_protocol["parent_candidate_pool_sha256"] != digest(b3 / "candidate-pool.json"):
        raise ValueError("Cold seeds and fixed candidate pool differ")
    indices = pool["candidate_full_indices"]
    bank = case["full_bank"].select(indices)
    if bank.numbers.tolist() != pool["candidate_numbers"]:
        raise ValueError("Frozen proposal bank numbers differ")
    prepared_hashes = {view: p.evidence_sha256 for view, p in case["prepared"].items()}
    if prepared_hashes != cold_protocol["prepared_sha256"]:
        raise ValueError("Cold-control training observations differ")
    if cold_protocol["candidate_full_indices"] != indices:
        raise ValueError("Cold-control bank indices differ")
    proposals = []
    for index, p in enumerate(cold_protocol["proposals"]):
        proposals.append(
            {
                "proposal_id": PROPOSAL_IDS[index],
                "id": PROPOSAL_IDS[index],
                "source_kind": "cold",
                "source_start": index,
                "point_km": p["point_km"],
            }
        )
    for index, p in enumerate(pool["proposals"]):
        proposals.append(
            {
                "proposal_id": PROPOSAL_IDS[index + 3],
                "id": PROPOSAL_IDS[index + 3],
                "source_kind": "shape",
                "source_view": p["source_view"],
                "source_start": index,
                "point_km": p["point_km"],
            }
        )
    directory = OUTPUT / "local/shared-proposals-v1" / label
    root = Path(__file__).parents[1]
    sources = [
        Path(__file__),
        Path(shared.__file__),
        root / "src/leo/analysis/research/doppler_shape_shared_proposals.py",
        root / "src/leo/analysis/frozen_group_calibration.py",
        root / "src/leo/analysis/channel_group_calibration.py",
        root / "src/leo/application/channel_group_refinement.py",
        root / "src/leo/analysis/hard60_joint_clock.py",
    ]
    snapshots = {}
    for source in sources:
        target = directory / "source-snapshot" / source.name
        value = source.read_bytes()
        if target.exists() and target.read_bytes() != value:
            raise ValueError(f"Frozen shared-proposal source differs: {source.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
        snapshots[source.name] = digest(target)
    seed_parents = {}
    for view in case["prepared"]:
        cold_hash = cold_terminal["seed_sha256"][view]
        read_bound(cold / "seeds" / f"{view}.json", cold_hash, digest)
        seed_parents[view] = {
            "cold_sha256": cold_hash,
            "shape_sha256": digest(b3 / "seeds" / f"{view}.json"),
        }
    protocol = {
        "label": label,
        "model": "frozen-six-training-proposal-pool",
        "common_protocol_sha256": case["protocol_sha256"],
        "b3_terminal_sha256": digest(b3 / "terminal.json"),
        "b3_protocol_sha256": b3_terminal["protocol_sha256"],
        "b3_candidate_pool_sha256": digest(b3 / "candidate-pool.json"),
        "cold_terminal_sha256": digest(cold / "terminal.json"),
        "cold_protocol_sha256": cold_terminal["protocol_sha256"],
        "candidate_full_indices": indices,
        "candidate_numbers": bank.numbers.tolist(),
        "prepared_sha256": prepared_hashes,
        "proposals": proposals,
        "seed_parent_sha256": seed_parents,
        "source_snapshots": snapshots,
        "selection": "all three original cold plus all three shape proposals; no deduplication",
        "physical_correction_kind": "training-derived-initialization-function",
        "reference_usage": "none",
        "held_usage": "none",
        "candidate_additions": False,
    }
    immutable(directory / "protocol.json", protocol)
    bindings = {}
    for view, prepared in case["prepared"].items():
        cold_values = read_bound(
            cold / "seeds" / f"{view}.json", seed_parents[view]["cold_sha256"], digest
        )
        shape_values = read_bound(
            b3 / "seeds" / f"{view}.json", seed_parents[view]["shape_sha256"], digest
        )
        model = objective(prepared, bank, case["prior"], case["nodes"])
        entries = ordered_seed_entries(cold_values, shape_values, proposals)
        for entry in entries:
            entry.update(encode_initial_physical_seed(model, entry["vector"], entry["nuisance"]))
        path = directory / "seeds" / f"{view}.json"
        immutable(path, entries)
        bindings[view] = digest(path)
    terminal = {
        "state": "complete",
        "label": label,
        "protocol_sha256": digest(directory / "protocol.json"),
        "seed_sha256": bindings,
        "proposal_ids": list(PROPOSAL_IDS),
        "reference_usage": "none",
        "held_usage": "none",
    }
    immutable(directory / "terminal.json", terminal)
    print(
        json.dumps({"label": label, "state": "complete", "directory": str(directory)}), flush=True
    )
    return terminal


def load_shared_proposals(case):
    from ds21_common import OUTPUT, digest

    label = case["member"]["label"]
    directory = OUTPUT / "local/shared-proposals-v1" / label
    terminal = json.loads((directory / "terminal.json").read_bytes())
    protocol = read_bound(directory / "protocol.json", terminal["protocol_sha256"], digest)
    if (
        terminal.get("state") != "complete"
        or protocol["reference_usage"] != "none"
        or protocol["held_usage"] != "none"
    ):
        raise ValueError("Sealed reference-free shared proposals required")
    if protocol["common_protocol_sha256"] != case["protocol_sha256"]:
        raise ValueError("Shared proposal common discovery differs")
    if protocol["prepared_sha256"] != {k: p.evidence_sha256 for k, p in case["prepared"].items()}:
        raise ValueError("Shared proposal prepared training data differ")
    b3 = OUTPUT / "local/model-b-shape-fresh-absolute-hybrid-v3" / label
    cold = OUTPUT / "local/cold-start-control-v1" / label
    for path, key in (
        (b3 / "terminal.json", "b3_terminal_sha256"),
        (b3 / "protocol.json", "b3_protocol_sha256"),
        (b3 / "candidate-pool.json", "b3_candidate_pool_sha256"),
        (cold / "terminal.json", "cold_terminal_sha256"),
        (cold / "protocol.json", "cold_protocol_sha256"),
    ):
        read_bound(path, protocol[key], digest)
    for name, expected in protocol["source_snapshots"].items():
        if digest(directory / "source-snapshot" / name) != expected:
            raise ValueError("Shared proposal source snapshot differs")
    bank = case["full_bank"].select(protocol["candidate_full_indices"])
    if bank.numbers.tolist() != protocol["candidate_numbers"]:
        raise ValueError("Shared proposal candidate order differs")
    seeds = {}
    for view in case["prepared"]:
        parents = protocol["seed_parent_sha256"][view]
        read_bound(cold / "seeds" / f"{view}.json", parents["cold_sha256"], digest)
        read_bound(b3 / "seeds" / f"{view}.json", parents["shape_sha256"], digest)
        entries = read_bound(
            directory / "seeds" / f"{view}.json", terminal["seed_sha256"][view], digest
        )
        if tuple(e["proposal_id"] for e in entries) != PROPOSAL_IDS:
            raise ValueError("Shared proposal ordering differs")
        for entry in entries:
            if entry["orbit_timing"]["satellite_numbers"] != protocol["candidate_numbers"]:
                raise ValueError("Shared proposal physical timing order differs")
        seeds[view] = entries
    binding = {
        "directory": str(directory),
        "protocol_sha256": terminal["protocol_sha256"],
        "terminal_sha256": digest(directory / "terminal.json"),
    }
    return bank, seeds, binding


def load_case_with_proposals(label):
    from ds21_common import load_case

    case = load_case(label)
    case["bank"], case["proposal_seeds"], case["proposal_binding"] = load_shared_proposals(case)
    return case


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    build(parser.parse_args().label)
