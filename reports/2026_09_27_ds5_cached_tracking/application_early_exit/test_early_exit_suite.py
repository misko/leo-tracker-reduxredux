"""Preserve frozen experiment sources while avoiding global module collisions."""

import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PROTOTYPE = load("ds5_early_exit_frozen_prototype", "prototype.py")
with patch.dict(sys.modules, {"prototype": PROTOTYPE}):
    for filename in ("test_prototype.py", "test_validation.py", "test_results.py"):
        module = load("ds5_early_exit_frozen_" + filename[:-3], filename)
        for name, value in vars(module).items():
            if name.startswith("test_") and callable(value):
                globals()["test_" + filename[5:-3] + "_" + name[5:]] = value


@pytest.fixture(autouse=True)
def isolated_prototype_import():
    with patch.dict(sys.modules, {"prototype": PROTOTYPE}):
        yield
