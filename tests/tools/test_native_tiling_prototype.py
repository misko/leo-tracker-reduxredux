"""A research tiling build must preserve the installed peak-selection code."""

import importlib.util
from pathlib import Path

import pytest


def load_builder():
    path = Path(__file__).resolve().parents[2]/'reports'/(
        '2026_11_03_algo07_runtime_iteration005')/'build_prototype.py'
    spec = importlib.util.spec_from_file_location('native_tiling_build', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_named_kernel_function_is_replaced():
    old = 'import x\n\ndef grid():\n    return 1\n\ndef peaks():\n    return "heap"\n'
    new = 'def grid():\n    return 2\n\ndef peaks():\n    return "sort"\n'
    actual = load_builder().replace_function(old, new, 'grid')
    assert actual == old.replace('return 1', 'return 2')


@pytest.mark.parametrize('source', ['', 'def grid(): pass\ndef grid(): pass\n'])
def test_missing_or_duplicate_kernel_is_rejected(source):
    with pytest.raises(ValueError, match='exactly one'):
        load_builder().replace_function(source, 'def grid(): pass\n', 'grid')
