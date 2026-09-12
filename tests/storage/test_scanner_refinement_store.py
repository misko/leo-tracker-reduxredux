import pytest

from leo.analysis.starlink.refinement_comparison import comparison_metrics
from leo.presentation.scanner_refinement import render_scanner_refinement
from leo.storage.scanner_refinement import ScannerRefinementStore
from leo.storage.scanner_refinement_source import select_visits
from tests.scanner.refinement_fixtures import comparison_fixture


@pytest.mark.parametrize("sample_rate_hz", [5000000, 10000000])
def test_read_only_missing_does_not_create_paths_and_resume_publishes_exact_bytes(
    tmp_path, sample_rate_hz
):
    reader = ScannerRefinementStore(tmp_path)
    assert reader.status("scan-one").state == "not_started"
    assert list(tmp_path.iterdir()) == []
    evidence = comparison_fixture(sample_rate_hz=sample_rate_hz)
    writer = ScannerRefinementStore(tmp_path, read_only=False)
    writer.save_work(evidence)
    assert reader.status("scan-one").state == "partial"
    assert writer.work("scan-one") == evidence
    pngs = render_scanner_refinement(evidence)
    manifest = writer.publish(evidence, comparison_metrics(evidence.rows), pngs)
    assert writer.publish(evidence, comparison_metrics(evidence.rows), pngs) == manifest
    assert reader.status("scan-one").manifest == manifest
    assert manifest.schema_version == (2 if sample_rate_hz == 10000000 else 1)
    assert manifest.sample_rate_hz == sample_rate_hz
    assert reader.artifact("scan-one", "shift-recovery") == pngs["shift-recovery"]
    assert reader.evidence("scan-one") is not None
    path = tmp_path / "scanner-refinement-comparisons" / "scan-one" / "probe-comparison.png"
    path.write_bytes(b"damaged")
    with pytest.raises(ValueError):
        reader.artifact("scan-one", "probe-comparison")


def test_qnap_symlink_and_traversal_are_rejected(tmp_path):
    store = ScannerRefinementStore(tmp_path)
    with pytest.raises(ValueError):
        store.status("../escape")
    (tmp_path / "scanner-refinement-comparisons").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        store.status("scan-one")
    with pytest.raises(ValueError):
        ScannerRefinementStore(__import__("pathlib").Path("/mnt/qnap01/anything")).status(
            "scan-one"
        )


def test_unfinished_schedule_cannot_publish_complete_manifest(tmp_path):
    evidence = comparison_fixture().model_copy(update={"rows": ()})
    writer = ScannerRefinementStore(tmp_path, read_only=False)
    with pytest.raises(ValueError, match="schedule is not complete"):
        writer.publish(evidence, (), {})
    assert writer.status("scan-one").state == "not_started"


def test_visit_selection_is_bounded_and_covers_every_observed_target():
    targets = list(range(8)) * 300
    selected = select_visits(targets)
    assert len(selected) == 16
    assert {targets[i] for i in selected} == set(range(8))
    assert selected == select_visits(targets)
    assert select_visits([]) == ()
