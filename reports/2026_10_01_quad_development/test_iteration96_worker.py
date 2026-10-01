"""Verify the experiment changes only the iteration cap and wrapper target."""
import ast
from pathlib import Path


def test_worker_only_changes_two_iteration_caps():
    here = Path(__file__).resolve().parent
    original = (here/'run_seed_limit.py').read_text()
    assert original.count('max_iterations=64') == 2
    expected = original.replace(
        'Versioned cold start-count ablation; original acquisition and model unchanged.',
        'Versioned 96-iteration ablation; all other worker behavior unchanged.').replace(
        'max_iterations=64', 'max_iterations=96')
    assert ast.dump(ast.parse((here/'run_seed_limit_96.py').read_text())) == ast.dump(ast.parse(expected))


def test_wrapper_only_redirects_worker_and_preserves_startup_timer():
    here = Path(__file__).resolve().parent
    expected = (here/'run_one_start_blas.py').read_text().replace(
        'Compose the unchanged start-count worker with the existing BLAS acquisition.',
        'Compose the 96-iteration worker with unchanged optimized acquisition.').replace(
        'run_seed_limit', 'run_seed_limit_96')
    assert ast.dump(ast.parse((here/'run_one_start_blas_96.py').read_text())) == ast.dump(ast.parse(expected))
