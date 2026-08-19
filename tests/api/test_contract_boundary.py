from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.presentation.fixtures import build_fixture_repository, write_fixture_artifacts
from leo.presentation.models import RecordingDetailV1, SystemStatusV1


def test_python_fixture_round_trips_through_strict_presentation_contract(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    write_fixture_artifacts(artifact_root)
    repository = build_fixture_repository(artifact_root)

    detail = repository.recording_detail("retro-positive-68p7")
    assert detail is not None
    parsed = RecordingDetailV1.model_validate_json(detail.model_dump_json())
    assert parsed.schema_version == 1
    assert parsed.source_type.value == "TEST"
    assert parsed.analysis.current_run is not None
    assert parsed.analysis.current_run.is_current is True
    assert (
        SystemStatusV1.model_validate_json(repository.status().model_dump_json()).api_mode
        == "read_only"
    )

    inconsistent = detail.model_dump(mode="json")
    inconsistent["products"][0]["analysis_run_id"] = "run-other"
    with pytest.raises(ValidationError, match="share the current run ID"):
        RecordingDetailV1.model_validate(inconsistent)


def test_committed_typescript_contract_tracks_presentation_v1() -> None:
    generated = Path("web/src/contracts.generated.ts").read_text()
    required_contract_fragments = (
        "PRESENTATION_SCHEMA_VERSION = 1",
        'export type SourceType = "LIVE" | "TEST" | "IMPORT"',
        'export type StorageState = "available" | "purged"',
        "export type AnalysisState =",
        'api_mode: "read_only"',
        "current_run: CurrentRunV1 | null",
        "whole_dwell:",
        "analysis_run_id: string | null",
        "compute_tier: ComputeTier",
        "confidence: ScientificConfidence",
        '"controls"',
        '"overlays"',
        "products: AnalysisProductV1[]",
    )
    for fragment in required_contract_fragments:
        assert fragment in generated
