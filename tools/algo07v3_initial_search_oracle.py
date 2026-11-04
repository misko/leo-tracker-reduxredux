"""External reference extraction for initial-search equivalence tests only.

Executes the frozen fit_case numerical body, removing only file publication,
progress printing and preparation. Explicit test budgets are applied to both
implementations. This tool is never imported by the standalone analyzer.
"""
import ast
import inspect

RESULT_FIELDS = (
    'status', 'GPS_used', 'choices', 'selected_hypothesis', 'zero_phase_control',
    'selection', 'unique_RF_hypotheses', 'fully_fitted_hypotheses',
    'same_observations_candidates_priors_bounds_and_budgets_in_c_pair',
    'fresh_radio_seed_budget', 'RF_proposal_points', 'region_center', 'box_width_km',
    'noise_sigma_hz',
)


def reference_initial_search(scan, sigma, *, seed_budget=4, branch_budget=3,
                             rounds=5, iterations=48):
    import evaluate_ds23_phase_refreshed as original
    import investigate_dsx01_localization_failures as numerical

    # The reference refresh function uses the default 48-step fit internally.
    # Rebind only that callable for a declared bounded test; preserve its body.
    refresh_globals = dict(numerical.refreshed.__globals__)
    refresh_globals['fit'] = lambda problem, start=(0., 0.): numerical.fit(
        problem, start, iterations=iterations)
    exec(compile(inspect.getsource(numerical.refreshed),
                 inspect.getsourcefile(numerical.refreshed), 'exec'), refresh_globals)
    refreshed = refresh_globals['refreshed']
    namespace = dict(original.fit_case.__globals__)
    namespace.update(scan=scan, sigma=sigma,
        fresh_discovery=lambda s, noise, budget: original.fresh_discovery(
            s, noise, budget=seed_budget),
        refreshed=lambda s, noise, node, arm: refreshed(s, noise, node, arm, rounds=rounds),
        fit=lambda problem: numerical.fit(problem, iterations=iterations))
    function = ast.parse(inspect.getsource(original.fit_case)).body[0]
    start = next(i for i, node in enumerate(function.body) if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'candidates' for t in node.targets))
    body = function.body[start:-1]

    class PublicationAndBudget(ast.NodeTransformer):
        def visit_Expr(self, node):
            if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                    and node.value.func.id in ('write', 'print')):
                return None
            return self.generic_visit(node)

        def visit_Assign(self, node):
            if any(isinstance(t, ast.Name) and t.id == 'selected' for t in node.targets):
                assert isinstance(node.value, ast.Subscript)
                assert isinstance(node.value.slice, ast.Slice)
                assert node.value.slice.upper.value == 3
                node.value.slice.upper = ast.Constant(branch_budget)
            return self.generic_visit(node)

    # Keep the original scientific result fields and exclude operational paths,
    # wall-clock timing and input guard bookkeeping from the numerical oracle.
    output = function.body[-1].value.args[1]
    assert isinstance(output, ast.Call) and output.func.id == 'dict'
    output.keywords = [kw for kw in output.keywords if kw.arg in RESULT_FIELDS]
    for keyword in output.keywords:
        if keyword.arg == 'fresh_radio_seed_budget':
            keyword.value = ast.Constant(seed_budget)
    body.append(ast.Assign(targets=[ast.Name(id='result', ctx=ast.Store())], value=output))
    module = PublicationAndBudget().visit(ast.Module(body=body, type_ignores=[]))
    exec(compile(ast.fix_missing_locations(module), inspect.getsourcefile(original), 'exec'),
         namespace)
    return namespace['result']


def reference_conservative_recovery(scan, initial, observations):
    """Original full-budget inference body, with explicit numerical inputs only."""
    import run_algo01_ds23_sample as original
    from audit_ds23_algo01_coverage import coverage
    from evaluate_ds23_phase_refreshed import extend_associations
    from propagate_ds23_arc_positions import PositionNormal

    function = ast.parse(inspect.getsource(original.infer)).body[0]
    start = next(i for i, node in enumerate(function.body) if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'winner' for t in node.targets))
    function.body = function.body[start:]
    function.name = 'numerical_recovery'
    function.args = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in
        ('scan', 'original', 'observations')], kwonlyargs=[], kw_defaults=[], defaults=[])

    class ExplicitInputsAndOutput(ast.NodeTransformer):
        def visit_Assign(self, node):
            if any(isinstance(t, ast.Name) and t.id in ('scan', 'observations')
                   for t in node.targets):
                return None
            return self.generic_visit(node)

        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                if node.value.func.id == 'print':
                    return None
                if node.value.func.id == 'write':
                    output = node.value.args[1]
                    assert isinstance(output, ast.Call) and output.func.id == 'dict'
                    output.keywords = [k for k in output.keywords
                                       if k.arg not in ('case', 'algorithm', 'source_sha256',
                                                        'seconds')]
                    return ast.Return(value=output)
            return self.generic_visit(node)

    namespace = dict(original.infer.__globals__)
    import numpy as np

    namespace.update(np=np, PositionNormal=PositionNormal, coverage=coverage,
                     extend_associations=extend_associations)
    module = ast.Module(body=[ExplicitInputsAndOutput().visit(function)], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), inspect.getsourcefile(original), 'exec'),
         namespace)
    return namespace['numerical_recovery'](scan, initial, observations)


def reference_history_policy(scan, original_result, raw, forecast, history_sha256):
    """Execute the frozen family-policy body with already bound explicit inputs."""
    import algo02_scan as original

    function = ast.parse(inspect.getsource(original.infer_algo02)).body[0]
    imports = [node for node in function.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    start = next(i for i, node in enumerate(function.body) if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'common' for t in node.targets))
    function.body = imports+function.body[start:]
    function.name = 'numerical_history'
    function.args = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in
        ('scan', 'original', 'raw', 'forecast', 'history_sha256')],
        kwonlyargs=[], kw_defaults=[], defaults=[])

    class ExplicitInputsAndOutput(ast.NodeTransformer):
        def visit_Assign(self, node):
            if any(isinstance(t, ast.Name) and t.id in
                   ('scan', 'history_root', 'raw_path', 'forecast_path') for t in node.targets):
                return None
            return self.generic_visit(node)

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == 'validate_history':
                node.args = [ast.Name(id=n, ctx=ast.Load()) for n in
                             ('raw', 'forecast', 'scan', 'history_sha256')]
            node.keywords = [kw for kw in node.keywords if kw.arg not in
                ('case', 'algorithm', 'baseline_sha256', 'engine_sha256',
                 'history_sha256', 'history_forecast_sha256', 'seconds')]
            return self.generic_visit(node)

        def visit_Expr(self, node):
            if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                    and node.value.func.id in ('write', 'print')):
                return None
            return self.generic_visit(node)

    namespace = dict(original.infer_algo02.__globals__)
    module = ast.Module(body=[ExplicitInputsAndOutput().visit(function)], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), inspect.getsourcefile(original), 'exec'),
         namespace)
    return namespace['numerical_history'](scan, original_result, raw, forecast, history_sha256)
