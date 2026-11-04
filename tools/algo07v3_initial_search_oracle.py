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
