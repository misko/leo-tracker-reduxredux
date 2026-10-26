"""Regression plus oracle equivalence for the original ranked-family rule."""
import ast
import hashlib
import json
import math
from pathlib import Path
import random

from selector_v2 import nominate

ORIGINAL = Path('/srv/bulk/leo/research/ds24-detector-response-r01/influence')


def original_rule():
    """Execute the original selection statements, not a rewritten oracle."""
    text = (ORIGINAL / 'panel.py').read_text()
    tree = ast.parse(text)
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    loop = next(n for n in ast.walk(run) if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == 'd')
    names = {'ranked', 'target_family', 'target', 'low', 'fscore', 'controls', 'control'}
    selected = []
    for node in loop.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            selected.append(node)
        elif isinstance(node, ast.Expr) and ast.unparse(node).startswith('controls.sort('):
            selected.append(node)
    assert len(selected) == 8, 'Original source shape changed; review extraction'
    body = [selected[0], ast.parse('if not ranked:\n return None, None').body[0], *selected[1:], ast.parse('return target, control').body[0]]
    fn = ast.FunctionDef(name='reference', args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='casefamilies'), ast.arg(arg='caseowners')], kwonlyargs=[], kw_defaults=[], defaults=[]), body=body, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    scope = {'math': math}
    exec(compile(module, str(ORIGINAL / 'panel.py') + ':selection', 'exec'), scope)
    return scope['reference']


def panel(count):
    families = [dict(family=i, paired_score=float(count-i), has_eligible_owner=True) for i in range(count)]
    owners = [dict(family=i, owner=f'T{i:03}', paired_score=float(count-i), receiver=1, eligible=True) for i in range(count)]
    return families, owners


def test_full_ranked_denominator_changes_cross_receiver_control():
    families, owners = panel(5)
    owners[3]['receiver'] = 2
    target, control = nominate(families, owners)
    assert target['family'] == 0
    assert control['family'] == 3
    # The old copied ceil(4/4) keeps only family4 and misses this witness.
    assert control['family'] != min(families[1:], key=lambda f: f['paired_score'])['family']
    assert (target, control) == original_rule()(families, owners)


def test_empty_and_single_family_have_no_invented_control():
    assert nominate([], []) == (None, None)
    families, owners = panel(1)
    assert nominate(families, owners) == (owners[0], None)


def test_original_source_equivalence_with_ties_zeros_and_multiple_owners():
    ref = original_rule()
    rng = random.Random(90210)
    for count in range(1, 33):
        families, owners = panel(count)
        for f, o in zip(families, owners):
            f['paired_score'] = rng.choice([0., 1., 2., 3.])
            f['has_eligible_owner'] = rng.random() > .2
            o['eligible'] = f['has_eligible_owner']
            o['receiver'] = rng.choice([1, 2])
            o['paired_score'] = rng.choice([0., 1., 2., 3.])
        owners += [dict(o, owner=o['owner']+'b', receiver=3-o['receiver']) for o in owners[:3]]
        rng.shuffle(families)
        rng.shuffle(owners)
        assert nominate(families, owners) == ref(families, owners)


def test_archived_complete_owner_choices_are_unchanged():
    saved = json.loads((ORIGINAL / 'results.json').read_text())
    for old in saved['selection']:
        case = old['case']
        families = [f for f in saved['families'] if f['case'] == case]
        owners = [o for o in saved['owners'] if o['case'] == case]
        target, control = nominate(families, owners)
        assert (target, control) == original_rule()(families, owners)
        assert target == old['target'] and control == old['control']
