from __future__ import annotations

import ast
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
