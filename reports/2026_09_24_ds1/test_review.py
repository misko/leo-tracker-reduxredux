"""Independent checks for the sealed DS1 dataset contract."""

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent


def _dataset():
    path = HERE / "dataset.json"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == (HERE / "dataset.sha256").read_text().strip()
    return json.loads(path.read_text())


def test_exact_partition_counts_priors_and_case_count():
    data = _dataset()
    assert data["name"] == "DS1"
    assert data["partition_counts"] == {"train": 151, "validation": 124, "test": 64}
    assert data["priors"] == {
        "sacramento": [38.5816, -121.4944, 250.0],
        "reno": [39.5296, -119.8138, 500.0],
    }
    assert len(data["groups"]) == 5
    assert len(data["cases"]) == 20


def test_cases_are_exact_ordered_nested_prefixes_of_one_group():
    data = _dataset()
    groups = {group["group_id"]: group for group in data["groups"]}
    for case in data["cases"]:
        group = groups[case["group_id"]]
        assert case["partition"] == group["partition"]
        assert case["scan_count"] == len(case["session_ids"])
        assert case["session_ids"] == group["session_ids"][: case["scan_count"]]
        assert case["view"] in {"1", "6", "16", "all"}
    assert data["views_are_nested_not_independent"] is True


def test_partitions_are_disjoint_and_full_test_failure_stays_in_all_view():
    data = _dataset()
    groups = data["groups"]
    partition_ids = {
        partition: {
            session_id
            for group in groups
            if group["partition"] == partition
            for session_id in group["session_ids"]
        }
        for partition in ("train", "validation", "test")
    }
    assert not (partition_ids["train"] & partition_ids["validation"])
    assert not (partition_ids["train"] & partition_ids["test"])
    assert not (partition_ids["validation"] & partition_ids["test"])
    full_test = next(case for case in data["cases"] if case["case_id"] == "test_20260922_00_all")
    assert full_test["session_ids"][47] == "scan-hop-6cd2560365a058bc"


def _runner():
    spec = importlib.util.spec_from_file_location("ds1_review_runner", HERE / "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Search:
    @staticmethod
    def offset_coordinate(centre, east_km, north_km):
        return centre[0] + north_km / 100, centre[1] + east_km / 100

    @staticmethod
    def haversine_km(left, right):
        return float(np.hypot((right[0] - left[0]) * 100, (right[1] - left[1]) * 100))


class _Engine:
    def __init__(self):
        self.search = _Search()
        self.sessions = [
            {
                "tracks": [
                    {"times": np.array([0.0, 4.0]), "weight": 5},
                ]
            }
        ]
        self.bindings = [{"session_id": "synthetic", "receipt": "r", "cache": "c"}]
        self.calls = []

    def profile(self, latitude_deg, longitude_deg, taus, held, assignments):
        # The runner's capped-square loss scale is deliberate: a seed loss of
        # 0.25 corresponds to a historical 400-Hz capped RMSE.
        self.calls.append((bool(held), bool(assignments)))
        taus = np.asarray(taus, dtype=float)
        loss = 0.25 + (latitude_deg - 0.04) ** 2 + (longitude_deg + 0.03) ** 2
        loss = loss + (taus - 0.3) ** 2 / 100
        return np.asarray(loss), np.zeros_like(taus), [[] for _ in taus]


def _run_synthetic_arm(monkeypatch, tmp_path):
    runner = _runner()
    protocol = tmp_path / "PROTOCOL.md"
    protocol.write_text("synthetic\n")
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"priors": {"sacramento": [0.0, 0.0, 100.0]}}))
    seed_file = tmp_path / "seed.json"
    seed_file.write_text("{}\n")
    engine = _Engine()
    seed = {
        "selected": {
            "latitude_deg": 0.0,
            "longitude_deg": 0.0,
            "objective_rmse_hz": float(
                np.sqrt(0.25 + 0.04**2 + 0.03**2 + 0.3**2 / 100) * 800
            ),
        }
    }
    case = {
        "case_id": "synthetic_1",
        "partition": "train",
        "group_id": "synthetic",
        "scan_count": 1,
        "session_ids": ["synthetic"],
    }
    monkeypatch.setattr(runner, "HERE", tmp_path)
    monkeypatch.setattr(runner, "DATA", dataset)
    monkeypatch.setattr(runner, "CLOCK", HERE / "run.py")
    module = type("M", (), {"SEARCH": HERE / "run.py"})
    monkeypatch.setattr(runner, "make_engine", lambda _case: (module, engine))
    monkeypatch.setattr(runner, "seed_search", lambda _case, _prior: seed)
    monkeypatch.setattr(runner, "seed_path", lambda _case: seed_file)
    runner.run_arm((case, "sacramento"))
    return engine, json.loads((tmp_path / "inference" / "synthetic_1__sacramento.json").read_text())


def test_staged_runner_retains_common_union_and_never_requests_held(monkeypatch, tmp_path):
    engine, result = _run_synthetic_arm(monkeypatch, tmp_path)
    assert result["seed_tau0_reproduced_rmse_hz"] == pytest.approx(
        np.sqrt(0.25 + 0.04**2 + 0.03**2 + 0.3**2 / 100) * 800
    )
    assert all(held is False and assignments is False for held, assignments in engine.calls)

    rows = result["visited_pairs"]
    by_location = {}
    for row in rows:
        by_location.setdefault((row["latitude_deg"], row["longitude_deg"]), set()).add(row["tau_s"])
    # Every retained geographic point is scored by both models through tau=0.
    assert all(0.0 in taus for taus in by_location.values())

    for previous, current in zip(result["levels"], result["levels"][1:], strict=False):
        assert current["pair_count"] >= previous["pair_count"]
        assert (
            current["baseline"]["training_capped_loss"]
            <= previous["baseline"]["training_capped_loss"]
        )
        assert (
            current["shared"]["training_capped_loss"]
            <= previous["shared"]["training_capped_loss"]
        )


def test_arm_output_is_not_overwritten(monkeypatch, tmp_path):
    _run_synthetic_arm(monkeypatch, tmp_path)
    runner = _runner()
    runner.HERE = tmp_path
    case = {"case_id": "synthetic_1", "session_ids": ["synthetic"]}
    with pytest.raises(FileExistsError, match="refusing overwrite"):
        runner.run_arm((case, "sacramento"))
