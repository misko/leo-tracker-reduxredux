from pathlib import Path

import pytest

from reports.ALGO08.v3 import original_dense_intake as trial


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
