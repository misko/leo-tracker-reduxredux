import pytest
from evaluate_experiment import planned_cells, require_complete


def test_missing_cell_prevents_reference_evaluation(tmp_path):
    protocol = {"sessions": ["scan"], "models": ["direct", "gem"], "tolerances": ["medium"]}
    directory = tmp_path / "runs/scan/direct-medium"
    directory.mkdir(parents=True)
    (directory / "fit.json").write_text("{}")
    with pytest.raises(ValueError, match="all planned"):
        require_complete(tmp_path, protocol)
    failed = tmp_path / "runs/scan/gem-medium"
    failed.mkdir()
    (failed / "failure.json").write_text("{}")
    require_complete(tmp_path, protocol)
    assert len(planned_cells(protocol)) == 2
