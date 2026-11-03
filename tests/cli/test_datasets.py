import hashlib
import json

import pytest
from typer.testing import CliRunner

from leo.cli.app import create_cli
from leo.cli.datasets import DatasetCatalogue, DatasetSummary, load_catalogue
from tools.build_dataset_catalogue import AuthorityReader, scan_metadata, summarise


def invoke(*arguments):
    def forbidden_backend():
        raise AssertionError("dataset inventory must not create a DB/radio backend")

    return CliRunner().invoke(
        create_cli(backend_factory=forbidden_backend), ["datasets", "list", *arguments]
    )


def test_real_catalogue_matches_frozen_membership_counts():
    result = invoke("--json")
    assert result.exit_code == 0, result.exception
    rows = {row["dataset"]: row for row in json.loads(result.stdout)["datasets"]}
    assert rows["DS1"]["scans"] == 339
    assert rows["DS4"]["scans"] == 91
    assert rows["DS23"]["scan_types"]["fast"] == 207
    assert rows["DS23"]["scan_types"]["adaptive"] == 206
    assert rows["DS24"]["scans"] == 103
    assert rows["DS25"]["scans"] == 69
    assert rows["DS26"]["scan_types"] == {"fast": 159, "adaptive": 158, "hop": 0, "unknown": 0}
    assert rows["DS27"]["scans"] == 28
    assert rows["DS28"]["scans"] == 16
    assert rows["DSX01"]["scans"] == 5
    assert rows["DS14"]["scans"] is None


def test_filter_counts_selected_type_and_preserves_full_membership():
    result = invoke("--dataset", "ds24", "--scan-type", "fast", "--json")
    assert result.exit_code == 0, result.exception
    (row,) = json.loads(result.stdout)["datasets"]
    assert row["membership_scans"] == 103
    assert row["scans"] == 34
    assert row["scan_types"]["adaptive"] == 0
    assert row["breakdown"] == [{"scan_type": "fast", "sample_rate_hz": 10_000_000, "scans": 34}]


def test_adaptive_only_dataset_is_not_misrepresented_as_fast():
    result = invoke("-d", "DS25", "--scan-type", "fast", "--json")
    assert result.exit_code == 0, result.exception
    (row,) = json.loads(result.stdout)["datasets"]
    assert row["scans"] == 0
    assert row["membership_scans"] == 69


def test_all_revisions_are_separate_not_added_together():
    result = invoke("-d", "DS24", "-d", "DS28", "--all-revisions", "--json")
    assert result.exit_code == 0, result.exception
    rows = json.loads(result.stdout)["datasets"]
    assert [(r["dataset"], r["revision"], r["scans"]) for r in rows] == [
        ("DS24", "1", 19),
        ("DS24", "2", 103),
        ("DS28", "1", 8),
        ("DS28", "2", 16),
    ]


def test_text_output_has_sample_rate_counts_and_unknowns():
    result = invoke("-d", "DS24", "-d", "DS14", "-d", "DS1")
    assert result.exit_code == 0, result.exception
    assert "MS/s: scans" in result.stdout
    assert "10: 103" in result.stdout
    assert "unknown: 339" in result.stdout
    assert "unlocated" in result.stdout
    assert "Datasets overlap" in result.stdout


def test_unknown_dataset_is_an_error():
    result = invoke("--dataset", "DS404")
    assert result.exit_code == 2
    assert "Unknown dataset(s): DS404" in result.stderr


def test_invalid_catalogue_does_not_silently_hide_bad_counts(tmp_path):
    path = tmp_path / "catalogue.json"
    path.write_text(
        json.dumps(
            {
                "generated_utc": "2026-11-03T00:00:00Z",
                "datasets": [
                    {
                        "dataset": "DS99",
                        "scans": 2,
                        "breakdown": [
                            {"scan_type": "fast", "scans": 1, "sample_rate_hz": 10_000_000}
                        ],
                    }
                ],
            }
        )
    )
    result = invoke("--catalogue", str(path))
    assert result.exit_code == 2
    assert "breakdown must sum" in result.stderr


def test_custom_catalogue_is_supported(tmp_path):
    path = tmp_path / "catalogue.json"
    catalogue = DatasetCatalogue(
        generated_utc="2026-11-03T00:00:00Z",
        datasets=[
            summarise(
                {"members": [{"recording_id": "fast-test", "sample_rate_hz": 7_500_000}]},
                dataset="DS99",
            )
        ],
    )
    path.write_text(catalogue.model_dump_json())
    result = invoke("--catalogue", str(path), "--json")
    assert result.exit_code == 0, result.exception
    assert json.loads(result.stdout)["datasets"][0]["breakdown"][0]["sample_rate_hz"] == 7_500_000


def test_nested_ds1_views_count_unique_acquisitions_and_not_cases():
    summary = summarise(
        {
            "groups": [
                {"session_ids": ["scan-hop-a", "scan-hop-b"]},
                {"session_ids": ["scan-hop-b"]},
            ],
            "cases": [{"session_ids": ["scan-hop-a"]}],
        },
        dataset="DS1",
    )
    assert summary.scans == 2
    assert summary.breakdown[0].sample_rate_hz is None


def test_excluded_capture_is_not_dataset_membership():
    summary = summarise(
        {
            "counts": {"admitted": 1},
            "captures": [
                {
                    "session_id": "scan-fw-in",
                    "admission_status": "included",
                    "sample_rate_hz": 2_500_000,
                },
                {
                    "session_id": "scan-fw-out",
                    "admission_status": "excluded",
                    "sample_rate_hz": 10_000_000,
                },
            ],
        },
        dataset="DS4",
    )
    assert summary.scans == 1
    assert summary.breakdown[0].sample_rate_hz == 2_500_000


def test_capture_rates_ignore_restoration_and_analysis_settings():
    member = {
        "recording_id": "fast-test",
        "raw_recording": {
            "segments": [
                {
                    "document": {
                        "kind": "short_window_iq_recording",
                        "configuration": {"sample_rate_hz": 10_000_000},
                        "restoration": {"sample_rate_hz": 61_440_000},
                    }
                }
            ]
        },
        "analysis": {"sample_rate_hz": 2_500_000},
    }
    assert scan_metadata(member) == ("fast", 10_000_000)


def test_adaptive_plan_wins_over_nested_hop_geometry():
    assert scan_metadata(
        {
            "session_id": "scan-fw-a",
            "plan": {
                "kind": "starlink_adaptive_hop_plan",
                "geometry": {"kind": "starlink_persistent_hop_plan", "sample_rate_hz": 5_000_000},
            },
        }
    ) == ("adaptive", 5_000_000)


def test_unknown_mode_is_not_guessed_from_sample_rate():
    assert scan_metadata({"session_id": "mystery", "sample_rate_hz": 10_000_000}) == (
        "unknown",
        10_000_000,
    )
    assert scan_metadata({"session_id": "scan-fw-a", "sample_rate_hz": 10_000_000}) == (
        "hop",
        10_000_000,
    )


@pytest.mark.parametrize(
    "document",
    [
        {"members": [{"recording_id": "a"}, {"recording_id": "a"}]},
        {"members": [{"recording_id": "a"}], "counts": {"members": 2}},
        {
            "members": [
                {
                    "recording_id": "fast-a",
                    "sample_rate_hz": 10_000_000,
                    "timing": {"sample_rate_hz": 2_500_000},
                }
            ]
        },
    ],
)
def test_ambiguous_or_inconsistent_membership_fails(document):
    with pytest.raises(ValueError):
        summarise(document, dataset="DS99")


def test_recording_metadata_must_match_pinned_checksum(tmp_path):
    path = tmp_path / "manifest.json"
    raw = b'{"kind":"starlink_adaptive_hop_iq","sample_rate_hz":10000000}'
    path.write_bytes(raw)
    member = {
        "recording_id": "a",
        "raw_recording": {
            "segments": [{"path": str(path), "sha256": "sha256:" + hashlib.sha256(raw).hexdigest()}]
        },
    }
    reader = AuthorityReader(tmp_path, [])
    summary = summarise(
        {"members": [member]}, dataset="DS99", resolve_metadata=reader.recording_metadata
    )
    assert summary.breakdown[0].scan_type == "adaptive"
    assert summary.breakdown[0].sample_rate_hz == 10_000_000
    path.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="changed capture metadata"):
        reader.recording_metadata(member)


def test_packaged_catalogue_is_valid_and_has_one_current_revision():
    catalogue = load_catalogue()
    assert len([row for row in catalogue.datasets if row.current and row.dataset == "DS24"]) == 1
    with pytest.raises(ValueError, match="breakdown must sum"):
        DatasetSummary(dataset="DS99", scans=1)


def test_archive_parts_are_decompressed_and_verified(tmp_path, monkeypatch):
    import zstandard

    from tools import build_dataset_catalogue as builder

    document = b'{"members":[{"recording_id":"fast-a","sample_rate_hz":10000000}]}'
    compressed = zstandard.ZstdCompressor().compress(document)
    archive = tmp_path / builder.ARCHIVE
    archive.mkdir(parents=True)
    parts = []
    for index, raw in enumerate((compressed[:8], compressed[8:])):
        name = f"DS99.manifest.json.zst.part{index:03d}"
        (archive / name).write_bytes(raw)
        parts.append({"path": name, "bytes": len(raw), "sha256": builder.sha256(raw)})
    authority = {
        "dataset": "DS99",
        "encoding": "concatenated-zstd-parts",
        "original_sha256": builder.sha256(document),
        "original_bytes": len(document),
        "parts": parts,
    }
    (archive / "catalogue.json").write_text(json.dumps({"authorities": [authority]}))
    monkeypatch.setattr(builder, "EXTRA_AUTHORITIES", ())
    catalogue = builder.build_catalogue(AuthorityReader(tmp_path, []))
    (row,) = [row for row in catalogue.datasets if row.dataset == "DS99"]
    assert row.scans == 1
    assert row.breakdown[0].sample_rate_hz == 10_000_000
    (archive / parts[1]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="archive part checksum/length mismatch"):
        builder.build_catalogue(AuthorityReader(tmp_path, []))
