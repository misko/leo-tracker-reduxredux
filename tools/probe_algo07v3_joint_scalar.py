"""External scalar-only joint-score prototype; owned runtime is unchanged."""

import ast
import inspect

from leo.analysis.localization_v3 import joint_density


def candidate(source=None):
    source = source or inspect.getsource(joint_density.two_family_phase_evidence)
    tree = ast.parse(source)
    function = tree.body[0]
    if not isinstance(function, ast.FunctionDef):
        raise ValueError('Review changed joint-score boundaries')
    tail = function.body[-4:]
    expected = ('evidence = float(logsumexp(log_joint))',
                'weights = np.exp(log_joint - evidence) if np.isfinite(evidence) '
                'else np.zeros(counts)',
                'k = np.unravel_index(int(np.argmax(log_joint)), tuple(counts))')
    if len(tail) != 4 or tuple(map(ast.unparse, tail[:3])) != expected:
        raise ValueError('Review changed joint-score boundaries')
    returned = tail[-1]
    if (not isinstance(returned, ast.Return) or not isinstance(returned.value, ast.Call)
            or ast.unparse(returned.value.func) != 'dict'):
        raise ValueError('Review changed joint-score boundaries')
    scores = [kw.value for kw in returned.value.keywords if kw.arg == 'negative_twice_log_density']
    maps = [n for n in ast.walk(function) if isinstance(n, ast.If)
            and ast.unparse(n.test) == 'score > best']
    if len(scores) != 1 or ast.unparse(scores[0]) != '-2 * evidence' or len(maps) != 1:
        raise ValueError('Review changed joint-score boundaries')
    function.body = function.body[:-3] + [ast.Return(value=scores[0])]

    class RemoveDiagnostics(ast.NodeTransformer):
        def visit_Assign(self, node):
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id in ('best', 'best_coeff', 'flat', 'score')):
                return None
            return self.generic_visit(node)

        def visit_If(self, node):
            return None if node is maps[0] else self.generic_visit(node)

    tree = ast.fix_missing_locations(RemoveDiagnostics().visit(tree))
    scope = dict(vars(joint_density))
    exec(compile(tree, '<v3-scalar-joint-probe>', 'exec'), scope)
    return scope['two_family_phase_evidence'], ast.unparse(tree)
