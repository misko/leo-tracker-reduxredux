import hashlib
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DIRECTORY = Path(__file__).parents[2] / "tools/research"
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location(
    "refine_five_block_position", DIRECTORY / "refine_five_block_position.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
SEAL_SPEC = importlib.util.spec_from_file_location(
    "seal_five_block_acquisition", DIRECTORY / "seal_five_block_acquisition.py"
)
SEAL_MODULE = importlib.util.module_from_spec(SEAL_SPEC)
assert SEAL_SPEC.loader is not None
SEAL_SPEC.loader.exec_module(SEAL_MODULE)


def write_acquisition(path, partition=MODULE.PARTITION):
    path.mkdir()
    source = {
        "tracklet_id": "track",
        "partition_digest": "sha256:partition",
        "full_training": 3,
        "full_heldout": 2,
        "selected_training": 3,
        "selected_heldout": 2,
    }
    receipt = {
        "partition": partition,
        "documents": [
            {
                "max_per_partition": 6,
                "episodes": [{"episode_id": "episode", "sources": [source]}],
            }
        ],
    }
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    receipt["content_digest"] = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    receipt_path = path / "partition-receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    (path / "result.json").write_text(
        json.dumps(
            {
                "partition": partition,
                "partition_receipt_digest": receipt["content_digest"],
                "max_per_partition": 6,
            }
        )
    )
    (path / "acquisition-seal.json").write_text(
        json.dumps({"files": {"partition-receipt.json": MODULE.digest(receipt_path)}})
    )
    return receipt


def test_acquisition_policy_and_uncapped_refinement_are_bound(tmp_path):
    receipt = write_acquisition(tmp_path / "run")
    _, verified = MODULE.verify_partition_acquisition(tmp_path / "run")
    assert verified == receipt
    refinement = json.loads(json.dumps(receipt["documents"]))
    MODULE.verify_uncapped_partition(receipt, refinement)
    refinement[0]["episodes"][0]["sources"][0]["selected_training"] = 2
    with pytest.raises(ValueError, match="restore every"):
        MODULE.verify_uncapped_partition(receipt, refinement)


def test_single_session_refinement_may_use_exact_partition_subset(tmp_path):
    receipt = write_acquisition(tmp_path / "run")
    extra = json.loads(json.dumps(receipt["documents"][0]))
    extra["episodes"][0]["episode_id"] = "other-episode"
    receipt["documents"].append(extra)
    subset = [receipt["documents"][0]]
    MODULE.verify_uncapped_partition(receipt, subset, allow_subset=True)
    with pytest.raises(ValueError, match="omits acquisition"):
        MODULE.verify_uncapped_partition(receipt, subset)


def test_wrong_partition_arm_is_rejected(tmp_path):
    write_acquisition(tmp_path / "run", partition="chronological")
    with pytest.raises(ValueError, match="declared five-block"):
        MODULE.verify_partition_acquisition(tmp_path / "run")


def test_refinement_private_replay_uses_five_block_loader():
    replay = SimpleNamespace(load_observations=lambda *_args, **_kwargs: "wrong-arm")
    base = SimpleNamespace(replay_module=lambda: replay)
    adapter = importlib.import_module("replay_five_block_regional")
    loader = MODULE.bind_five_block_replay(base, adapter)
    result = base.replay_module().load_observations(
        {
            "series": [
                {
                    "tracklet_id": "track",
                    "t_s": list(range(10)),
                    "y_hz": list(range(10)),
                    "candidate_ids": [f"observation-{index}" for index in range(10)],
                    "actual_rf_hz": 10.8e9,
                    "channel": 1,
                }
            ],
            "episodes": [{"episode_id": "episode", "members": ["track"]}],
        },
        max_per_partition=0,
    )
    assert result[0][1].training.tolist() == [True] * 6 + [False] * 4
    assert result[0][1].time_s.tolist() == [0, 1, 4, 5, 8, 9, 2, 3, 6, 7]
    assert loader.documents[0]["partition"] == MODULE.PARTITION


def test_sealer_recomputes_partition_receipt_digest():
    receipt = {"partition": MODULE.PARTITION, "documents": []}
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    receipt["content_digest"] = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    SEAL_MODULE.verify_partition_receipt(receipt)
    receipt["documents"].append({"poisoned": True})
    with pytest.raises(ValueError, match="content digest mismatch"):
        SEAL_MODULE.verify_partition_receipt(receipt)


def test_completed_refinement_gets_content_seal(tmp_path):
    acquisition = tmp_path / "acquisition"
    acquisition.mkdir()
    (acquisition / "acquisition-seal.json").write_text("{}")
    output = tmp_path / "output"
    output.mkdir()
    result = {
        "complete": True,
        "position_truth_used": False,
        "fits": [{"converged": True}],
        "five_block_adapter_digest": "sha256:adapter",
        "five_block_wrapper_digest": "sha256:wrapper",
        "base_refiner_digest": "sha256:base",
        "numerical_source_digest": "sha256:core",
        "observation_count": 10,
        "sessions": ["scan"],
    }
    (output / "result.json").write_text(json.dumps(result))
    (output / "result.sha256").write_text("checksum\n")
    MODULE.seal_refinement(output, acquisition, result, {"content_digest": "sha256:partition"})
    seal = json.loads((output / "refinement-seal.json").read_text())
    assert seal["all_fits_converged"] is True
    assert seal["partition_receipt_digest"] == "sha256:partition"
    assert seal["result_digest"] == MODULE.digest(output / "result.json")
