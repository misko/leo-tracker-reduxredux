#!/usr/bin/env python3
"""Run the existing position refiner with a sealed five-block partition."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from seal_five_block_acquisition import PARTITION, digest


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _content_digest(value: dict[str, object]) -> str:
    body = dict(value)
    claimed = body.pop("content_digest", None)
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    actual = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    if claimed != actual:
        raise ValueError("partition receipt content digest mismatch")
    return actual


def verify_partition_acquisition(run: Path) -> tuple[dict, dict]:
    result = json.loads((run / "result.json").read_text())
    receipt = json.loads((run / "partition-receipt.json").read_text())
    receipt_digest = _content_digest(receipt)
    if (
        result.get("partition") != PARTITION
        or result.get("partition_receipt_digest") != receipt_digest
        or receipt.get("partition") != PARTITION
        or result.get("max_per_partition") != 6
        or any(row.get("max_per_partition") != 6 for row in receipt.get("documents", []))
    ):
        raise ValueError("acquisition does not use the declared five-block policy")
    seal = json.loads((run / "acquisition-seal.json").read_text())
    expected = seal.get("files", {}).get("partition-receipt.json")
    if expected != digest(run / "partition-receipt.json"):
        raise ValueError("acquisition seal does not bind the partition receipt")
    return result, receipt


def verify_uncapped_partition(
    acquisition: dict, refinement: list[dict[str, object]], *, allow_subset: bool = False
) -> None:
    expected = {
        (episode["episode_id"], source["tracklet_id"]): source["partition_digest"]
        for document in acquisition["documents"]
        for episode in document["episodes"]
        for source in episode["sources"]
    }
    actual = {
        (episode["episode_id"], source["tracklet_id"]): source["partition_digest"]
        for document in refinement
        for episode in document["episodes"]
        for source in episode["sources"]
    }
    if not actual or any(expected.get(key) != value for key, value in actual.items()):
        raise ValueError("uncapped refinement partition differs from acquisition policy")
    if not allow_subset and actual != expected:
        raise ValueError("full refinement omits acquisition partition support")
    if any(
        source["selected_training"] != source["full_training"]
        or source["selected_heldout"] != source["full_heldout"]
        for document in refinement
        for episode in document["episodes"]
        for source in episode["sources"]
    ):
        raise ValueError("refinement did not restore every partitioned observation")


def bind_five_block_replay(base, adapter):
    """Bind the private refiner module to this adapter without changing shared modules."""
    private_replay = base.replay_module()
    loader = adapter.FiveBlockLoader()
    private_replay.load_observations = loader
    base.replay_module = lambda: private_replay
    return loader


def run(args) -> None:
    _result, acquisition_receipt = verify_partition_acquisition(args.run)
    directory = Path(__file__).parent
    adapter_path = directory / "replay_five_block_regional.py"
    base_path = directory / "refine_recent_joint_position.py"
    if not base_path.is_file():
        base_path = directory.parents[1] / "research/refine_recent_joint_position.py"
    adapter = _load(adapter_path, "five_block_adapter_for_refinement")
    base = _load(base_path, "five_block_base_refiner")
    loader = bind_five_block_replay(base, adapter)
    base.run(args)
    verify_uncapped_partition(
        acquisition_receipt, loader.documents, allow_subset=args.single_session is not None
    )
    path = args.output / "result.json"
    result = json.loads(path.read_text())
    result.update(
        {
            "partition": PARTITION,
            "partition_receipt_digest": acquisition_receipt["content_digest"],
            "partition_interpretation": (
                "full-span interpolation/shape CV; not future forecasting"
            ),
            "five_block_adapter_digest": digest(adapter_path),
            "five_block_wrapper_digest": digest(Path(__file__)),
            "base_refiner_digest": digest(base_path),
        }
    )
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(payload)
    (args.output / "result.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--single-session")
    parser.add_argument("--modes", type=int, default=3)
    parser.add_argument("--max-evaluations", type=int, default=140)
    parser.add_argument("--budget-seconds", type=float, default=900)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
