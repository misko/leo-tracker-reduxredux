import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def child(code):
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(ROOT / "src"),
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    return subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )


def test_actual_original_collision_reproduced_without_recordings():
    result = child(f"""
import sys, importlib.util
from pathlib import Path
root=Path({str(ROOT)!r})
sys.path.insert(0,str(root/'reports/2026_10_10_position_error_iter136'))
import run
sys.path.insert(0,str(root/'reports/2026_10_09_position_error_iter116'))
run.module('entry116_regression',root/'reports/2026_10_09_position_error_iter116/entrypoint.py')
""")
    assert result.returncode != 0
    assert "cannot import name 'PointEvaluator' from 'adapter'" in result.stderr


def test_successor_imports_actual_legacy_driver_and_preserves_math():
    result = child(f"""
import sys
from pathlib import Path
root=Path({str(ROOT)!r})
sys.path.insert(0,str(root/'reports/2026_10_10_position_error_iter138'))
import run
assert 'adapter' not in sys.modules
assert 'pair_score' not in sys.modules
assert 'audit_core' not in sys.modules
assert Path(run.implementation.audit.__code__.co_filename).parent.name.endswith('iter136')
assert Path(run.implementation.adapt_support.__code__.co_filename).parent.name.endswith('iter136')
sys.path.insert(0,str(root/'reports/2026_10_09_position_error_iter116'))
entry=run.implementation.module('entry116_regression',root/'reports/2026_10_09_position_error_iter116/entrypoint.py')
import driver, adapter
assert driver.PointEvaluator is adapter.PointEvaluator
assert Path(adapter.__file__).parent.name.endswith('iter116')
assert callable(entry.make_loader)
assert run.implementation.HERE.name.endswith('iter138')
""")
    assert result.returncode == 0, result.stderr


def test_preexisting_alias_is_restored():
    result = child(f"""
import sys, types
sys.path.insert(0,{str(HERE)!r})
sentinel=types.ModuleType('adapter')
sys.modules['adapter']=sentinel
import run
assert sys.modules['adapter'] is sentinel
assert run.implementation.adapt_support.__module__=='audit136_for138_adapter'
""")
    assert result.returncode == 0, result.stderr
