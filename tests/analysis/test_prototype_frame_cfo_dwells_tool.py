from __future__ import annotations

import copy
import csv
import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from leo.analysis.research.frame_cfo_dwell_prototype import PrototypeRegionRole

ROOT = Path(__file__).parents[2]
INPUTS_PATH = ROOT / "config" / "analysis" / "frame-cfo-prototype-v1.json"


def _tool() -> ModuleType:
    path = ROOT / "tools" / "prototype_frame_cfo_dwells.py"
    spec = importlib.util.spec_from_file_location("prototype_frame_cfo_dwells_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _inputs() -> dict[str, object]:
    document = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _row(
    tool: ModuleType,
    *,
    trajectory_id: str,
    alias_index: int,
    frame_start_sample: int,
    role: str = "middle_median_margin",
) -> object:
    return tool.FrameCfoPrototypeRow(
        row_id=f"row-{trajectory_id}-{frame_start_sample}",
        region_id=f"region-{role}",
        region_role=PrototypeRegionRole(role),
        strong_interior_opportunity=True,
        trajectory_id=trajectory_id,
        branch_id="branch",
        trajectory_alias_index=alias_index,
        canonical_observation_id="canonical-observation",
        source_observation_id="raw-observation",
        observation_alias_index=0,
        frame_index=frame_start_sample // 100,
        frame_start_sample=frame_start_sample,
        frame_time_s=frame_start_sample / 1_000.0,
        continuity_segment=0,
        crosses_refill_boundary=False,
        raw_source_cfo_hz=101_250.0,
        source_bound_seed_hz=101_250.0 + alias_index * 750_000.0,
        trajectory_model_cfo_hz=101_200.0 + alias_index * 750_000.0,
        primary=None,
        sensitivity=None,
        split_validation=None,
    )


def _validation(
    *,
    status: str = "complete",
    local_rms_hz: float = 105.0,
    model_rms_hz: float = 100.0,
    rate_difference_hz_s: float = 499.999,
    improvement_fraction: float = 0.20,
    sigma_hz_s: float = 1_000.0,
) -> dict[str, object]:
    return {
        "status": status,
        "reason": "test fixture",
        "even_selected_frame_count": 30,
        "fitted_frame_count": 30,
        "ramp_count": 3,
        "local_odd_validation_rms_hz": local_rms_hz,
        "trajectory_odd_validation_rms_hz": model_rms_hz,
        "rate_difference_hz_s": rate_difference_hz_s,
        "odd_validation_improvement_fraction": improvement_fraction,
        "local_rate_conditional_sigma_hz_s": sigma_hz_s,
        "odd_symbols_influenced_membership": False,
    }


def _hypothesis(
    trajectory_id: str,
    alias_index: int,
    *,
    validation: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "trajectory_id": trajectory_id,
        "branch_id": "branch",
        "alias_index": alias_index,
        "diagnostic_frame_count": 24,
        "strong_interior_retention_fraction": 0.75,
        "even_odd_p95_hz": 100.0,
        "timing_spread_p95_hz": 50.0,
        "half_frame_difference_p95_z": 4.0,
        "tone_deletion_spread_p95_hz": 75.0,
        "strong_search_boundary_fraction": 0.049999,
        "sensitivity_substitution_count": 0,
        "heldout_validation": validation or _validation(),
    }


def _dwell(label: str, aliases: tuple[int, ...]) -> dict[str, object]:
    phase = "explore" if label in {"470384", "T01", "T06"} else "confirm"
    hypotheses = [
        _hypothesis(f"{label}-alias-{alias_index:+d}", alias_index) for alias_index in aliases
    ]
    return {
        "label": label,
        "phase": phase,
        "selected_region_count": 6,
        "pinned_alias_indices": list(aliases),
        "evaluation_trajectory_id": hypotheses[0]["trajectory_id"],
        "hypotheses": hypotheses,
    }


def _five_dwells() -> list[dict[str, object]]:
    return [
        _dwell("470384", (0,)),
        _dwell("T01", (-1, 0)),
        _dwell("T06", (0, 1)),
        _dwell("T04", (-1, 0)),
        _dwell("T03", (-1, 0)),
    ]


def _gate_result(
    report: dict[str, object],
    name: str,
    *,
    dwell: str,
    trajectory_id: str | None = None,
) -> dict[str, object]:
    matches = [
        item
        for item in report["results"]
        if item["name"] == name
        and item["dwell"] == dwell
        and (trajectory_id is None or item["trajectory_id"] == trajectory_id)
    ]
    assert len(matches) == 1
    return matches[0]


def test_frozen_inputs_pin_exact_version_pairs_and_alias_hypothesis_ids() -> None:
    tool = _tool()
    document = _inputs()

    inventory = tool._validate_inputs(document)

    assert tool.canonical_digest(document) == (
        "sha256:47faac16930a60aab4b66fcb91d0385e581f9d60faa083a312e4875407c2e1e4"
    )
    assert [item["label"] for item in inventory] == ["470384", "T01", "T06", "T04", "T03"]
    assert {
        item["label"]: (
            item["dealiased_product_version"],
            item["final_product_version"],
            item["branch_id"],
            tuple(item["trajectory_ids"]),
        )
        for item in inventory
    } == {
        "470384": (
            3,
            2,
            "sha256:5852a9363eb59b0ebd3f20eb82fc21ef912f1eeeeb1af0c508609d8e1425af30",
            ("sha256:f751bbe5a13af4ba0481e6d434fc5a373c5a95a64c55aa0df8b80a86963ca601",),
        ),
        "T01": (
            4,
            3,
            "sha256:84df3b60e86ecfc2454e659a8b94038048b9a9841664f2fdd67d471cbc35f3d7",
            (
                "sha256:6ae9ef2b5aa90b3bbb9802217448db5fc8fb2677ee31d8948bd28dd1ba6dd09c",
                "sha256:83ef7b0317c86416f5e1b13a1e34d1c661eff4bd1229f1f947ed567b4403822e",
            ),
        ),
        "T06": (
            4,
            3,
            "sha256:5f852fa252038288a4438b4291960543bed3e6956bdad17d04a1be7eacc0e7d9",
            (
                "sha256:2bff3b061a18ed774c5cce47460d8ad7d9ea453a8b8e33712a72b254bbcff848",
                "sha256:d04127698d6d235706822be1586e21ab07aff33d78c4641b2ea77ee5805f057c",
            ),
        ),
        "T04": (
            4,
            3,
            "sha256:f60d8949ae0890640a886476e3e2ba0b03641c0460597d7907b3bd05746d40de",
            (
                "sha256:5bea03bd71ac6ac89e808ee35ee0dac6e230dfbd43323fb3db5f91348b97fd06",
                "sha256:e52e1cb8b1ce2626d0daca2ff05d22134b7ed7c13e099a589a463a162be03334",
            ),
        ),
        "T03": (
            4,
            3,
            "sha256:135e3b71ac80a98ae6ea5bd38586cd8c5599c84b1c70b3780c19c0e1dfbbaa23",
            (
                "sha256:a0876414db2523fd6c6876336ceb664e75b197320c1dacdc64b7940afdfce488",
                "sha256:f106ccd250e32654d7424a1e29988be892d1c992e3e88a1bd86d2b5fb15731be",
            ),
        ),
    }


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("open_fields", "fields are not closed"),
        ("duplicate_label", "labels must be unique strings"),
        ("non_string_label", "labels must be unique strings"),
        ("unsupported_version_pair", "unsupported dealiased/final product version pair"),
        ("duplicate_trajectory", "trajectory IDs must be unique"),
    ),
)
def test_input_validation_rejects_unfrozen_or_ambiguous_identifiers(
    case: str,
    message: str,
) -> None:
    tool = _tool()
    document = copy.deepcopy(_inputs())
    dwells = document["dwells"]
    assert isinstance(dwells, list)
    first = dwells[0]
    second = dwells[1]
    assert isinstance(first, dict) and isinstance(second, dict)

    if case == "open_fields":
        first["unreviewed_field"] = True
    elif case == "duplicate_label":
        second["label"] = first["label"]
    elif case == "non_string_label":
        first["label"] = 470384
    elif case == "unsupported_version_pair":
        first["final_product_version"] = 3
    elif case == "duplicate_trajectory":
        trajectory_ids = second["trajectory_ids"]
        assert isinstance(trajectory_ids, list)
        trajectory_ids[1] = trajectory_ids[0]
    else:  # pragma: no cover - guards the table itself
        raise AssertionError(case)

    with pytest.raises(ValueError, match=message):
        tool._validate_inputs(document)


def test_row_writers_are_sorted_and_byte_deterministic(tmp_path: Path) -> None:
    tool = _tool()
    rows = [
        ("T06", "explore", _row(tool, trajectory_id="z", alias_index=1, frame_start_sample=300)),
        ("T01", "explore", _row(tool, trajectory_id="b", alias_index=0, frame_start_sample=200)),
        ("T01", "explore", _row(tool, trajectory_id="a", alias_index=-1, frame_start_sample=100)),
    ]
    gzip_one = tmp_path / "one.jsonl.gz"
    gzip_two = tmp_path / "two.jsonl.gz"
    csv_one = tmp_path / "one.csv"
    csv_two = tmp_path / "two.csv"

    tool._write_rows(gzip_one, rows)
    tool._write_rows(gzip_two, list(reversed(rows)))
    tool._write_csv(csv_one, rows)
    tool._write_csv(csv_two, list(reversed(rows)))

    compressed = gzip_one.read_bytes()
    assert compressed == gzip_two.read_bytes()
    assert compressed[:4] == b"\x1f\x8b\x08\x00"
    assert int.from_bytes(compressed[4:8], "little") == 0
    json_rows = [json.loads(line) for line in gzip.decompress(compressed).splitlines()]
    assert [
        (item["dwell_label"], item["trajectory_alias_index"], item["trajectory_id"])
        for item in json_rows
    ] == [("T01", -1, "a"), ("T01", 0, "b"), ("T06", 1, "z")]
    assert all(
        item["schema"] == "org.leo.research.frame-cfo-prototype-row/v1" for item in json_rows
    )

    assert csv_one.read_bytes() == csv_two.read_bytes()
    assert b"\r\n" not in csv_one.read_bytes()
    with csv_one.open(newline="", encoding="utf-8") as source:
        csv_rows = list(csv.DictReader(source))
    assert [
        (item["dwell_label"], item["alias_index"], item["trajectory_id"]) for item in csv_rows
    ] == [("T01", "-1", "a"), ("T01", "0", "b"), ("T06", "1", "z")]


def test_gate_evaluator_accepts_declared_edges_only_for_a_full_run() -> None:
    tool = _tool()
    dwells = _five_dwells()

    full = tool._gates(dwells, full_run=True)
    smoke = tool._gates(dwells, full_run=False)

    assert full["passed"] is True
    assert full["failed_gate_count"] == 0
    assert full["gate_count"] == len(full["results"])
    assert smoke["passed"] is False
    assert smoke["failed_gate_count"] == 0
    assert smoke["evaluation_scope"] == "bounded smoke only"


def test_gate_evaluator_uses_strict_search_boundary_and_t06_rate_limits() -> None:
    tool = _tool()
    dwells = _five_dwells()
    dwells[0]["hypotheses"][0]["strong_search_boundary_fraction"] = 0.05
    t06 = dwells[2]["hypotheses"][0]
    t06["heldout_validation"]["rate_difference_hz_s"] = -500.0

    report = tool._gates(dwells, full_run=True)

    boundary = _gate_result(
        report,
        "strong_search_boundary_fraction",
        dwell="470384",
        trajectory_id="470384-alias-+0",
    )
    rate = _gate_result(
        report,
        "t06_no_bias_rate_control",
        dwell="T06",
        trajectory_id="T06-alias-+0",
    )
    assert boundary["passed"] is False
    assert rate["passed"] is False
    assert report["passed"] is False


def test_gate_evaluator_keeps_heldout_and_regression_failures_separate() -> None:
    tool = _tool()
    dwells = _five_dwells()
    t01 = dwells[1]["hypotheses"][0]
    t01["heldout_validation"]["local_odd_validation_rms_hz"] = 105.001
    t01["heldout_validation"]["odd_validation_improvement_fraction"] = 0.199
    t03 = dwells[4]["hypotheses"][0]
    t03["heldout_validation"]["status"] = "insufficient"

    report = tool._gates(dwells, full_run=True)

    assert (
        _gate_result(
            report,
            "heldout_not_worse",
            dwell="T01",
            trajectory_id="T01-alias--1",
        )["passed"]
        is False
    )
    assert (
        _gate_result(
            report,
            "reset_biased_heldout_improvement",
            dwell="T01",
            trajectory_id="T01-alias--1",
        )["passed"]
        is False
    )
    assert (
        _gate_result(
            report,
            "heldout_not_worse",
            dwell="T03",
            trajectory_id="T03-alias--1",
        )["passed"]
        is False
    )
    assert (
        _gate_result(
            report,
            "t03_fail_closed_or_stable",
            dwell="T03",
            trajectory_id="T03-alias--1",
        )["passed"]
        is True
    )
    assert report["passed"] is False


def test_gate_evaluator_rejects_collapsed_alias_hypotheses() -> None:
    tool = _tool()
    dwell = _dwell("T01", (-1, 0))
    dwell["pinned_alias_indices"] = [-1, -1]

    report = tool._gates([dwell], full_run=True)

    assert _gate_result(report, "alias_hypotheses_preserved", dwell="T01")["passed"] is False
    assert report["passed"] is False


def test_mocked_smoke_run_creates_a_self_consistent_artifact_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    bulk_root = tmp_path / "bulk"
    bulk_root.mkdir()
    stores = []

    class FakeStore:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    def open_pinned(_pinned: object) -> FakeStore:
        store = FakeStore()
        stores.append(store)
        return store

    def analyze_dwell(**kwargs: object) -> tuple[dict[str, object], tuple[object, ...]]:
        item = kwargs["item"]
        assert isinstance(item, dict)
        trajectory_id = item["trajectory_ids"][0]
        dwell = _dwell(str(item["label"]), (0,))
        dwell["selected_region_count"] = kwargs["maximum_regions"]
        dwell["full_declared_region_count"] = 6
        dwell["hypotheses"][0]["trajectory_id"] = trajectory_id
        dwell["evaluation_trajectory_id"] = trajectory_id
        row = _row(
            tool,
            trajectory_id=trajectory_id,
            alias_index=0,
            frame_start_sample=1_000,
        )
        return dwell, (row,)

    def plot(path: Path, _rows: object) -> None:
        path.write_bytes(b"deterministic-test-figure\n")

    monkeypatch.setattr(tool.RecordingStore, "open_pinned", open_pinned)
    monkeypatch.setattr(tool, "analyze_dwell", analyze_dwell)
    monkeypatch.setattr(tool, "_plot", plot)

    documents = []
    output_roots = (tmp_path / "first", tmp_path / "second")
    for output_root in output_roots:
        documents.append(
            tool.run_prototype(
                bulk_root=bulk_root,
                inputs_path=INPUTS_PATH,
                output_root=output_root,
                phase="all",
                labels=("470384",),
                maximum_regions=1,
            )
        )

    assert all(store.closed for store in stores)
    assert documents[0] == documents[1]
    assert documents[0]["selection"]["full_frozen_run"] is False
    assert documents[0]["acceptance"]["passed"] is False
    assert documents[0]["candidate_only"] is True
    assert documents[0]["new_rf_collected"] is False

    artifact_names = {
        "frame-cfo-rows.jsonl.gz",
        "frame-cfo-rows.csv",
        "frame-cfo-prototype.png",
        "summary.json",
        "artifact-manifest.json",
    }
    assert {path.name for path in output_roots[0].iterdir()} == artifact_names
    for name in artifact_names:
        assert (output_roots[0] / name).read_bytes() == (output_roots[1] / name).read_bytes()

    manifest = json.loads((output_roots[0] / "artifact-manifest.json").read_text())
    for name, digest in manifest["artifacts"].items():
        assert digest == tool._sha256(output_roots[0] / name)
