import importlib
import sys

import pytest

from tools.pipeline_eval.variants.experimental import lean_startup


def test_package_reexports_load_the_original_symbol_only_on_access(tmp_path, monkeypatch):
    name = "lean_startup_export_fixture"
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text(
        f'"""Fixture exports."""\nfrom {name}.deferred import original as public\n'
        '__all__ = ["public"]\n'
    )
    (package / "deferred.py").write_text("original = object()\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(lean_startup, "FACADES", {name})
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    lean_startup.install()
    try:
        module = importlib.import_module(name)
        assert module.__doc__ == "Fixture exports."
        assert module.__all__ == ["public"] and "public" in dir(module)
        assert f"{name}.deferred" not in sys.modules
        value = module.public
        assert value is sys.modules[f"{name}.deferred"].original
        assert vars(module)["public"] is value
        with pytest.raises(AttributeError):
            _ = module.unknown
        with pytest.raises(RuntimeError, match="fresh"):
            lean_startup.install()
    finally:
        sys.modules.pop(f"{name}.deferred", None)
        sys.modules.pop(name, None)


@pytest.mark.parametrize("source", [
    'from pkg import exported\nregister()\n__all__ = ["exported"]',
    'from pkg import *\n__all__ = ["exported"]',
    'from .pkg import exported\n__all__ = ["exported"]',
    'from pkg import exported\n__all__ = ["missing"]',
    'from pkg import exported\n__all__ = names()',
])
def test_nonliteral_or_executable_setup_uses_the_stock_loader(source):
    assert lean_startup.reexports(source) is None
