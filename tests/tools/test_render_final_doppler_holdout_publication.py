from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tools import render_final_doppler_holdout_publication as publication

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCORE_PATH = REPOSITORY_ROOT / publication.SOURCE_SCORE_PATH


@pytest.fixture(scope="module")
def score() -> dict[str, Any]:
    return publication.load_frozen_score(SCORE_PATH, repository_root=REPOSITORY_ROOT)


def test_publication_source_is_exact_and_has_expected_science(
    score: dict[str, Any],
) -> None:
    publication.verify_frozen_source_artifacts(repository_root=REPOSITORY_ROOT)
    methods = {item["method"]: item for item in score["scores"]}
    assert {
        method: (
            item["equal_capture_rms_hz"],
            item["pooled_rms_hz"],
            item["prediction_complete_count"],
        )
        for method, item in methods.items()
    } == {
        "fixed_20ms_linear": (61.7472930318272, 50.26579245029935, 5_286),
        "fixed_125ms_linear": (57.75380979657822, 50.31471528105331, 5_399),
        "fixed_500ms_linear": (60.28885387873705, 52.76591174186161, 4_148),
        "lean_500ms_quadratic": (58.17047606219212, 50.96845505043494, 4_136),
    }
    assert score["quadratic_promotion_gate"] == {
        "capture_comparisons": 10,
        "capture_wins": 9,
        "completion_difference_percentage_points": 0.22168852761870195,
        "failed_conditions": [
            "equal_capture_rms_ratio_above_0_95",
            "capture_response_availability_below_50pct",
        ],
        "maximum_capture_ratio": 1.0062814746063935,
        "passed": False,
        "ratio": 0.9648628613705983,
    }


def test_publication_retry_amendment_and_path_normalization_are_exact(
    tmp_path: Path,
) -> None:
    amendment = publication.verify_publication_amendment(repository_root=REPOSITORY_ROOT)
    amendment_path = REPOSITORY_ROOT / publication.PUBLICATION_AMENDMENT_PATH
    assert "sha256:" + hashlib.sha256(amendment_path.read_bytes()).hexdigest() == (
        publication.PUBLICATION_AMENDMENT_SHA256
    )
    assert amendment["amendment_digest"] == publication.PUBLICATION_AMENDMENT_DIGEST

    root = tmp_path / "repository"
    root.mkdir()
    assert (
        publication._resolve_repository_path(Path("reports/publication.md"), repository_root=root)
        == (root / "reports/publication.md").resolve()
    )
    assert (
        publication._resolve_repository_path(root / "reports/publication.md", repository_root=root)
        == (root / "reports/publication.md").resolve()
    )
    with pytest.raises(ValueError, match="must remain inside"):
        publication._resolve_repository_path(Path("../outside.md"), repository_root=root)


@pytest.mark.parametrize("poison", ["figure_directory", "detailed_markdown_path"])
def test_wrong_retry_output_path_fails_before_score_load_or_render(
    poison: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def snapshot(path: Path) -> object:
        if not path.exists():
            return None
        if path.is_file():
            return publication._sha256_tag(path)
        return tuple(
            (item.relative_to(path).as_posix(), publication._sha256_tag(item))
            for item in sorted(path.rglob("*"))
            if item.is_file()
        )

    amendment = publication.verify_publication_amendment(repository_root=REPOSITORY_ROOT)
    retry = amendment["retry_authority"]
    output_dir = REPOSITORY_ROOT / retry["figure_directory"]
    markdown_path = REPOSITORY_ROOT / retry["detailed_markdown_path"]
    if poison == "figure_directory":
        output_dir = REPOSITORY_ROOT / "reports/figures/__never_write_publication_test"
    else:
        markdown_path = REPOSITORY_ROOT / "reports/__never_write_publication_test.md"
    wrong_path = output_dir if poison == "figure_directory" else markdown_path
    assert not wrong_path.exists()
    before_output = snapshot(output_dir)
    before_markdown = snapshot(markdown_path)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("score load or rendering occurred before retry-path rejection")

    monkeypatch.setattr(publication, "load_frozen_score", forbidden)
    monkeypatch.setattr(publication, "render_corrected_figures", forbidden)
    with pytest.raises(ValueError, match="differ from frozen amendment"):
        publication.render_publication(
            score_path=SCORE_PATH,
            output_dir=output_dir,
            markdown_path=markdown_path,
            repository_root=REPOSITORY_ROOT,
        )
    assert not wrong_path.exists()
    assert snapshot(output_dir) == before_output
    assert snapshot(markdown_path) == before_markdown


def test_association_rows_distinguish_track_recovery_from_identity(
    score: dict[str, Any],
) -> None:
    rows = publication.association_publication_rows(score)
    evaluable = [item for item in rows if item["evaluable"]]
    non_evaluable = [item for item in rows if not item["evaluable"]]
    assert len(evaluable) == 8
    assert len(non_evaluable) == 2
    assert sum(item["recovered_track"] for item in evaluable) == 8
    assert sum(item["catalog_compatible"] for item in evaluable) == 0
    assert sum(item["primary_baseline_agreement"] for item in evaluable) == 2
    assert sum(item["heldout_rank_one_remains_best"] for item in evaluable) == 2
    assert sum(item["rolling_stable"] for item in evaluable) == 1
    assert sum(item["conditions"]["wrong_time_empirical_p"] for item in evaluable) == 0
    assert sum(item["conditions"]["permutation_empirical_p"] for item in evaluable) == 7
    assert sum(item["conditions"]["required_permutations_scored"] for item in evaluable) == 8
    assert (
        sum(
            item["conditions"]["utc_site_predecessor_controls_complete_and_stable"]
            for item in evaluable
        )
        == 8
    )
    assert [
        len(item["primary"]["scores"]) for item in score["association"] if item["evaluable"]
    ] == [508, 528, 551, 535, 529, 530, 543, 520]
    assert tuple(item["session_id"] for item in non_evaluable) == (
        "cap-20260825T034929-bc0480bdb4a8",
        "cap-20260825T035201-d0abaead734c",
    )


def test_detailed_markdown_states_null_result_and_has_four_resolved_image_links(
    score: dict[str, Any],
    tmp_path: Path,
) -> None:
    markdown_path = tmp_path / "reports" / "detailed.md"
    figures = tmp_path / "figures"
    figures.mkdir()
    paths = [
        figures / "forecast.png",
        figures / "paired.png",
        figures / "association.png",
        figures / "gates.png",
    ]
    for path in paths:
        path.write_bytes(b"placeholder")
    manifest_path = figures / "manifest.json"
    manifest_path.write_text("{}")
    markdown = publication.build_detailed_markdown(
        score,
        markdown_path=markdown_path,
        forecast_figure=paths[0],
        paired_figure=paths[1],
        corrected_association_figure=paths[2],
        gate_matrix_figure=paths[3],
        publication_manifest=manifest_path,
    )

    assert "0/8 passed the\nfull catalog-compatibility gate" in markdown
    assert "no satellite was linked" in markdown
    assert "not an identity claim" in markdown
    assert "100 Hz ceiling" in markdown
    assert "Fixed 125 ms linear | 57.754" in markdown
    assert "Strict-past 500 ms quadratic | 58.170" in markdown
    assert "insufficient_total_bins" in markdown
    assert "508, 528, 551, 535, 529, 530, 543, 520" in markdown
    assert "Permutation empirical-p gate passes | 7/8" in markdown
    assert "training rank order were all frozen" in markdown
    assert "selected discriminating conditions plus the full gate" in markdown
    links = publication.markdown_image_links(markdown)
    assert len(links) == 4
    assert all((markdown_path.parent / link).resolve().is_file() for link in links)
    artifact_links = publication.markdown_artifact_links(markdown)
    assert len(artifact_links) == 6
    assert all((markdown_path.parent / link).resolve().is_file() for link in artifact_links)


def test_corrected_figures_use_failed_gate_and_non_evaluable_semantics(
    score: dict[str, Any],
    tmp_path: Path,
) -> None:
    first, second = publication.render_corrected_figures(score, output_dir=tmp_path)
    assert first.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert second.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert first.stat().st_size > 50_000
    assert second.stat().st_size > 50_000
    source = (REPOSITORY_ROOT / "tools/render_final_doppler_holdout_publication.py").read_text()
    assert "axis.set_title(ASSOCIATION_RMS_TITLE, pad=10)" in source
    assert (
        "All eight evaluable response tracks fail at least one required identity/null gate"
        not in source
    )


def test_renderer_has_no_storage_estimator_or_propagation_imports() -> None:
    source = (REPOSITORY_ROOT / "tools/render_final_doppler_holdout_publication.py").read_text()
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(
        name.startswith(prefix)
        for name in imports
        for prefix in (
            "leo.storage",
            "leo.analysis.qam",
            "leo.analysis.research.final_doppler_holdout",
            "leo.analysis.research.final_holdout_satellite",
            "leo.sky",
        )
    )


def test_attempt2_publication_artifacts_are_static_hash_and_link_closed() -> None:
    evidence_path = (
        REPOSITORY_ROOT / "reports/figures/2026_08_26_final_doppler_holdout_publication_attempt2/"
        "publication-execution-evidence.json"
    )
    assert publication._sha256_tag(evidence_path) == (
        "sha256:aeea27975d28829d35fc5a4fa3cf86c60520becaad98837a0af4559a0f2c6b44"
    )
    evidence = json.loads(evidence_path.read_text())
    assert evidence["evidence_manifest_digest"] == publication.canonical_digest(
        {key: value for key, value in evidence.items() if key != "evidence_manifest_digest"}
    )
    assert evidence["evidence_manifest_digest"] == (
        "sha256:7c3082029f0cbd7bcb9f023e3335484c45d8eb7b56ba887c203890fa11425f18"
    )
    for item in evidence["outputs"].values():
        path = REPOSITORY_ROOT / item["path"]
        assert path.stat().st_size == item["byte_size"]
        assert publication._sha256_tag(path) == item["sha256"]

    manifest_item = evidence["outputs"]["publication_manifest"]
    manifest_path = REPOSITORY_ROOT / manifest_item["path"]
    manifest = json.loads(manifest_path.read_text())
    assert manifest["manifest_digest"] == publication.canonical_digest(
        {key: value for key, value in manifest.items() if key != "manifest_digest"}
    )
    assert manifest["manifest_digest"] == manifest_item["semantic_digest"]
    assert manifest["renderer"]["execution_commit"] == ("16d74aea3beb42e948d7559cd47919ddbff708cb")
    assert manifest["renderer"]["execution_tree"] == ("1f4ac9838ae87e345b96c5f3e5fd72ad5712a7e0")
    assert manifest["publication_amendment"]["semantic_digest"] == (
        publication.PUBLICATION_AMENDMENT_DIGEST
    )

    markdown_path = REPOSITORY_ROOT / evidence["outputs"]["detailed_markdown"]["path"]
    markdown = markdown_path.read_text()
    assert "0/8 passed the\nfull catalog-compatibility gate" in markdown
    assert "no satellite was linked" in markdown
    assert "not an identity claim" in markdown
    assert "Fixed 125 ms linear | 57.754" in markdown
    assert "Strict-past 500 ms quadratic | 58.170" in markdown
    image_links = publication.markdown_image_links(markdown)
    artifact_links = publication.markdown_artifact_links(markdown)
    assert len(image_links) == 4
    assert len(artifact_links) == 6
    assert all(
        (markdown_path.parent / link).resolve().is_file()
        for link in (*image_links, *artifact_links)
    )

    publication.verify_frozen_source_artifacts(repository_root=REPOSITORY_ROOT)
    amendment = publication.verify_publication_amendment(repository_root=REPOSITORY_ROOT)
    failure = amendment["failure_attempt"]
    failure_evidence_path = REPOSITORY_ROOT / failure["evidence_path"]
    assert publication._sha256_tag(failure_evidence_path) == failure["evidence_sha256"]
    failure_evidence = json.loads(failure_evidence_path.read_text())
    for item in failure_evidence["partial_outputs"].values():
        if isinstance(item, dict):
            path = REPOSITORY_ROOT / item["path"]
            assert path.stat().st_size == item["byte_size"]
            assert publication._sha256_tag(path) == item["sha256"]
