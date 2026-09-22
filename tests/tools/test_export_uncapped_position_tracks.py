from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _subject():
    path = Path(__file__).parents[2] / "tools/research/export_uncapped_position_tracks.py"
    spec = importlib.util.spec_from_file_location("export_uncapped_position_tracks", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_only_accepts_exact_retry_and_rejects_changed_shard(tmp_path: Path) -> None:
    subject = _subject()
    path = tmp_path / "scan-one.json"

    subject._write_create_only(path, b'{"sealed":true}\n')
    subject._write_create_only(path, b'{"sealed":true}\n')

    assert path.read_bytes() == b'{"sealed":true}\n'
    with pytest.raises(FileExistsError, match="existing shard differs"):
        subject._write_create_only(path, b'{"sealed":false}\n')


def test_row_document_exports_only_rf_observation_and_fractional_source_fields() -> None:
    subject = _subject()

    class Row:
        observation_id = "observation"
        source_group_id = "group"
        support_start_utc_ns = 100
        support_center_utc_ns = 200
        support_end_utc_ns = 300
        measured_cfo_hz = 42.5
        standard_uncertainty_hz = 3.0
        source_sample_start = 10
        source_sample_end = 20

    class Source:
        candidate_rank = 2
        exact_score = 11.0
        control_score = 4.0
        margin = 7.0
        site_conditioned_candidate_id = "must-not-leak"

    assert subject._row_document(Row(), Source()) == {
        "observation_id": "observation",
        "source_group_id": "group",
        "support_start_utc_ns": 100,
        "support_center_utc_ns": 200,
        "support_end_utc_ns": 300,
        "measured_cfo_hz": 42.5,
        "standard_uncertainty_hz": 3.0,
        "fractional_candidate_rank": 2,
        "fractional_exact_score": 11.0,
        "fractional_control_score": 4.0,
        "fractional_margin": 7.0,
        "source_sample_start": 10,
        "source_sample_end": 20,
    }


def test_catalogue_reference_rejects_snapshot_at_causal_cutoff() -> None:
    subject = _subject()
    snapshot = SimpleNamespace(
        digest="sha256:" + "a" * 64,
        collected_utc_ns=1_000,
        provider="fixture",
        byte_size=1,
    )

    class Archive:
        def select_latest_before(self, _utc_ns: int):
            return snapshot

        def read(self, _snapshot):  # pragma: no cover - causal guard runs first
            raise AssertionError("noncausal snapshot must not be read")

    with pytest.raises(ValueError, match="non-causal snapshot"):
        subject._catalogue_reference(Archive(), 1_000)


def test_disjoint_selection_accounts_for_overlapping_source_groups() -> None:
    subject = _subject()
    leading = SimpleNamespace(tracklet_id="leading")
    overlapping = SimpleNamespace(tracklet_id="overlapping")
    independent = SimpleNamespace(tracklet_id="independent")

    def rows(*groups: str):
        return tuple(SimpleNamespace(source_group_id=value) for value in groups)

    accepted, excluded = subject._select_disjoint_tracklets(
        [(leading, rows("a", "b")), (overlapping, rows("b", "c")), (independent, rows("d"))]
    )

    assert [item[0].tracklet_id for item in accepted] == ["leading", "independent"]
    assert excluded == [
        {
            "tracklet_id": "overlapping",
            "observation_count": 2,
            "overlapping_source_group_count": 1,
            "overlapping_source_group_digest": subject.canonical_digest(["b"]),
        }
    ]
