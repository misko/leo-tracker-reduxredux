"""Frozen pre-change implementation for tests only; never a runtime dependency."""

import hashlib
import importlib.util
import inspect
from pathlib import Path

path = Path(__file__).with_name('fixtures') / 'joint_density_pre_layout.py'
assert hashlib.sha256(path.read_bytes()).hexdigest() == (
    'afacc375fdfb0750a497f2077f85c27ecdf51a56320de5aab77e00639595d9b4'
)
spec = importlib.util.spec_from_file_location('leo.analysis.localization_v3._pre_layout_test', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
reference = module.two_family_phase_evidence
reference_source = inspect.getsource(reference)
