"""Ensure the versioned runner changes only the intended start-count controls."""
import ast
from pathlib import Path


def test_only_seed_limit_controls_differ_from_original_runner():
    here = Path(__file__).resolve().parent
    original = (here/'run_window.py').read_text()
    expected = original.replace(
        '"""Cold single/dual/quad localization with independent scan nuisance blocks."""',
        '"""Versioned cold start-count ablation; original acquisition and model unchanged."""')
    expected = expected.replace("parser.add_argument('unit')",
        "parser.add_argument('unit')\n    parser.add_argument('--seed-limit', type=int, choices=(1, 3), required=True)")
    expected = expected.replace('seed_limit=3,max_iterations=64', 'seed_limit=args.seed_limit,max_iterations=64')
    expected = expected.replace('enumerate(seeds[:3])', 'enumerate(seeds[:args.seed_limit])')
    actual = (here/'run_seed_limit.py').read_text()
    assert ast.dump(ast.parse(actual)) == ast.dump(ast.parse(expected))
