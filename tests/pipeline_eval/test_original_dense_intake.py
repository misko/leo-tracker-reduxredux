from pathlib import Path

import pytest

from reports.ALGO08.v3 import original_dense_intake as trial
from reports.ALGO08.v3 import original_dense_intake_score as score


def test_guard_allows_only_the_bound_original_member_and_its_index():
    for name in trial.NAMES:
        trial.guard("open", (trial.INPUT / name,))
    with pytest.raises(PermissionError, match="outside the single"):
        trial.guard("open", (trial.INPUT / "iq-000001.ci16.zst",))
    with pytest.raises(PermissionError, match="backing files"):
        trial.guard("open", (Path("/srv/bulk/hidden/manifest.json"),))


def test_loader_only_adapts_the_pinned_scanner_import(tmp_path):
    (tmp_path / "algo08_scan.py").write_text("seen = 'released'\n")
    intercepted = []
    finder = trial.OnScannerImport(lambda module: intercepted.append(module.seen))
    assert finder.find_spec("tools.algo08_position", [str(tmp_path)]) is None
    spec = finder.find_spec("tools.algo08_scan", [str(tmp_path)])
    from importlib.util import module_from_spec

    loaded = module_from_spec(spec)
    spec.loader.exec_module(loaded)
    assert loaded.seen == "released" and intercepted == ["released"]


def test_rates_distinguish_true_file_boundary_and_inner_acquisition():
    measured = score.rates(77_442_779, 0.64, 0.68, 0.285)
    assert measured["through_detections"] == pytest.approx(121.0043421875)
    assert measured["inner_receiver"] < score.TARGET
    assert measured["required_seconds_at_target"] == pytest.approx(0.273552734)
    with pytest.raises(ValueError, match="ordered boundaries"):
        score.rates(77_442_779, 0.4, 0.68, 0.5)
