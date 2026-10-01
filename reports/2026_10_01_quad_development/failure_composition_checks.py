"""Strict preservation checks; matching solver failures alone never suffice."""
import numpy as np


def close(a, b, tolerance):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return bool(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all()
                and np.allclose(a, b, rtol=0, atol=tolerance))


def process_ok(launch):
    return bool(launch.get('returncode') == 0 and launch.get('within_budget')
                and launch.get('timed_out') is False
                and 0 <= launch.get('elapsed_seconds', float('inf'))
                <= launch.get('external_limit_seconds', -1))


def comparison_checks(receipts, parent, outcomes):
    saved = parent['fits'][0]
    checks = {'saved_failure': saved['converged'] is False
              and saved['reason'] == 'iteration_limit' and saved['iterations'] == 64}
    config = dict(parent['config'], seed_limit=1)
    for arm in ('original', 'blas'):
        receipt = receipts.get(arm) or {}
        outcome = outcomes.get(arm, {})
        checks[arm+'_processes'] = all(process_ok(outcome.get(key, {}))
                                       for key in ('launch', 'audit_launch'))
        rows = (outcome.get('evaluation') or {}).get('rows', [])
        checks[arm+'_audit_rejection'] = bool(len(rows) == 1
            and rows[0].get('unit') == parent['unit']
            and rows[0].get('accepted') is False
            and rows[0].get('fit_status') == 'unresolved'
            and rows[0].get('failures') == ['AssertionError: unresolved']
            and 'error_m' in rows[0] and rows[0]['error_m'] is None)
        checks[arm+'_status'] = receipt.get('status') == 'unresolved' and 'exception' not in receipt
        checks[arm+'_config'] = receipt.get('config') == config
        checks[arm+'_binding'] = all(k in receipt and receipt[k] == parent[k] for k in (
            'unit', 'binding', 'columns', 'precision', 'inputs', 'height', 'observations', 'model'))
        proposal = receipt.get('proposal', {})
        checks[arm+'_proposal'] = (all(proposal.get(k) == parent['proposal'][k]
            for k in ('seeds', 'requested', 'unique_points', 'spacing'))
            and close(proposal.get('scores', []), parent['proposal']['scores'], 1e-6))
        fits = receipt.get('fits', [])
        checks[arm+'_one_fit'] = len(fits) == 1 and receipt.get('best') == fits[0]
        if len(fits) != 1:
            continue
        fit = fits[0]
        checks[arm+'_discrete_fit'] = all(fit.get(k) == saved[k] for k in (
            'seed_index', 'converged', 'reason', 'iterations', 'associations'))
        checks[arm+'_state'] = close(fit.get('mean', []), saved['mean'], 1e-5)
        checks[arm+'_objective_history'] = close(fit.get('objectives', []), saved['objectives'], 1e-6)
    if all(len((receipts.get(a) or {}).get('fits', [])) == 1 for a in ('original', 'blas')):
        a, b = (receipts[k]['fits'][0] for k in ('original', 'blas'))
        checks['cross_arm_state'] = close(a['mean'], b['mean'], 1e-5)
        checks['cross_arm_objective_history'] = close(a['objectives'], b['objectives'], 1e-6)
    return checks
