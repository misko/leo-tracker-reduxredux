import importlib.util,sys
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("batch_extend",HERE/"batch_extend_orbits.py");assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=module;SPEC.loader.exec_module(module)


def test_batch_slices_exact_common_order(monkeypatch):
    units=[f"U{i:02d}" for i in range(64)];monkeypatch.setattr(module,"selected_units",lambda:units)
    assert module.batch_units(1)==units[:8]
    assert module.batch_units(2)==units[8:16]
    assert module.batch_units(8)==units[56:64]


def test_batch_number_is_bounded():
    with pytest.raises(ValueError,match="1..8"):module.batch_units(0)
    with pytest.raises(ValueError,match="1..8"):module.batch_units(9)


def test_child_command_passes_absolute_cache_without_home_override(tmp_path):
    command=module.child_command("DS9-F001",tmp_path/"cache")
    assert command[-2:]==["--cache-dir",str((tmp_path/"cache").resolve())]
    assert not any(part.startswith("HOME=") for part in command)
