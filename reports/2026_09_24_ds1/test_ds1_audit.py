"""Frozen DS1 membership and locally available cache-contract checks."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json"


def _resolved(root, session_id):
    return (root / session_id / "cache_receipt.json").is_file() and (
        root / session_id / "state_cache.npz"
    ).is_file()


def test_ds1_partitions_are_whole_group_disjoint_and_sized():
    partitions = json.loads(MANIFEST.read_text())["partitions"]
    assert {name: len(value["session_ids"]) for name, value in partitions.items()} == {
        "train": 151,
        "validation": 124,
        "test": 64,
    }
    groups = {name: set(value["groups"]) for name, value in partitions.items()}
    assert not (groups["train"] & groups["validation"])
    assert not (groups["train"] & groups["test"])
    assert not (groups["validation"] & groups["test"])
    ids = [session_id for value in partitions.values() for session_id in value["session_ids"]]
    assert len(ids) == len(set(ids)) == 339


def test_local_train_and_validation_caches_resolve_every_manifest_id():
    partitions = json.loads(MANIFEST.read_text())["partitions"]
    first = Path("/tmp/leo-long-training-cache-full8h")
    second = Path("/tmp/leo-long-training-cache-second8h")
    validation = Path("/tmp/leo-frozen-validation-cache")
    train = partitions["train"]["session_ids"]
    assert all(_resolved(first, session_id) for session_id in train[:72])
    assert all(_resolved(second, session_id) for session_id in train[72:])
    validation_ids = partitions["validation"]["session_ids"]
    assert all(_resolved(validation, session_id) for session_id in validation_ids)


def test_full_test_failure_is_explicit_and_never_silently_filtered():
    test_ids = json.loads(MANIFEST.read_text())["partitions"]["test"]["session_ids"]
    cache = Path("/tmp/leo-final-test-global-epoch-cache")
    missing = [session_id for session_id in test_ids if not _resolved(cache, session_id)]
    assert missing == ["scan-hop-6cd2560365a058bc"]
    assert test_ids.index(missing[0]) == 47
