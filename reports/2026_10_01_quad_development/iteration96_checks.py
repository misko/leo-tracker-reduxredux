"""Check the cap-only change and retain the full 64-iteration objective prefix."""
from failure_composition_checks import close


def compare(parent, receipt):
    receipt = receipt or {}
    baseline = parent['best']
    checks = dict(parent_policy=parent['config']['max_iterations'] == 64
                  and parent['config']['seed_limit'] == 1)
    checks['config'] = receipt.get('config') == dict(parent['config'], max_iterations=96)
    checks['binding'] = all(k in receipt and receipt[k] == parent[k] for k in (
        'unit', 'binding', 'columns', 'precision', 'inputs', 'height', 'observations', 'model'))
    proposal = receipt.get('proposal', {})
    checks['proposal'] = all(proposal.get(k) == parent['proposal'][k]
        for k in ('seeds', 'requested', 'unique_points', 'spacing')) and close(
        proposal.get('scores', []), parent['proposal']['scores'], 1e-6)
    fits = receipt.get('fits', [])
    checks['one_fit'] = len(fits) == 1 and receipt.get('best') == fits[0]
    if len(fits) != 1:
        return checks
    fit = fits[0]
    checks['seed_index'] = fit.get('seed_index') == baseline['seed_index'] == 0
    checks['iteration_cap'] = baseline['iterations'] <= fit.get('iterations', -1) <= 96
    checks['status_consistency'] = ('exception' not in receipt and receipt.get('status') ==
        ('converged_local_mode' if fit.get('converged') else 'unresolved'))
    history = fit.get('objectives', [])
    checks['objective_prefix'] = len(history) >= len(baseline['objectives']) and close(
        history[:len(baseline['objectives'])], baseline['objectives'], 1e-6)
    if baseline['converged']:
        checks['control_state'] = close(fit.get('mean', []), baseline['mean'], 1e-5)
        checks['control_history_length'] = len(history) == len(baseline['objectives'])
        checks['control_discrete_fit'] = all(fit.get(k) == baseline[k] for k in (
            'converged', 'reason', 'iterations', 'associations'))
    return checks
