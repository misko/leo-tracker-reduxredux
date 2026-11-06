"""External candidate removing one duplicate final joint integral per fit."""

import ast
import inspect

from leo.analysis.localization_v3 import joint_recovery


def candidate(name, source=None):
    if name not in ('_fit_lbfgsb', '_fit_powell'):
        raise ValueError('Explicit owned optimizer required')
    source = source or inspect.getsource(getattr(joint_recovery, name))
    tree = ast.parse(source)
    fn, = tree.body
    # Only the reporting tail changes. Optimization and ordered policy calls
    # remain verbatim, including all five phase-refresh rounds.
    density_calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                     and ast.unparse(n.func) == 'joint_density']
    if len(density_calls) != 1:
        raise ValueError('Review changed final-density boundary')
    final_call = density_calls[0]
    saved = ast.Assign(targets=[ast.Name(id='final_joint_result', ctx=ast.Store())],
                       value=final_call)
    joint_score = ast.parse(
        "result['joint_evidence'] = final_joint_result['negative_twice_log_density']"
    ).body[0]
    if name == '_fit_lbfgsb':
        scores = [n for n in fn.body if isinstance(n, ast.Assign)
                  and ast.unparse(n.targets[0]) == "result['joint_evidence']"]
        if len(scores) != 1 or ast.unparse(scores[0].value) != \
                "evidence(families, p, x, d, 'joint')":
            raise ValueError('Review changed joint-score boundary')
        index = fn.body.index(scores[0])
        fn.body[index:index + 1] = [saved, joint_score]
    else:
        loops = [n for n in fn.body if isinstance(n, ast.For)
                 and ast.unparse(n.iter) == "('joint', 'factorized')"]
        expected = "result[score_method + '_evidence'] = evidence(families, p, x, d, score_method)"
        if len(loops) != 1 or len(loops[0].body) != 1 or \
                ast.unparse(loops[0].body[0]) != expected:
            raise ValueError('Review changed joint-score boundary')
        index = fn.body.index(loops[0])
        factorized = ast.parse(
            "result['factorized_evidence'] = evidence(families, p, x, d, 'factorized')"
        ).body[0]
        fn.body[index:index + 1] = [saved, joint_score, factorized]

    class Reuse(ast.NodeTransformer):
        def visit_Assign(self, node):
            if node is saved:
                return node
            return self.generic_visit(node)

        def visit_Call(self, node):
            if node is final_call:
                return ast.Name(id='final_joint_result', ctx=ast.Load())
            return self.generic_visit(node)

    tree = ast.fix_missing_locations(Reuse().visit(tree))
    scope = dict(vars(joint_recovery))
    exec(compile(tree, '<final-joint-reuse-probe>', 'exec'), scope)
    return scope[name], ast.unparse(tree)
