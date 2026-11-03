"""Align BFGS stopping tolerance with the frozen 1e-5 gradient gate.

The initial run requested 1e-7 internally, which was stricter than the protocol's
1e-5 gate and produced a precision-loss termination at gradient6.75e-6. Preserve
that failed result. Reuse identical data, feature construction, zero seed, ridge,
objective, independent derivative audit and validation gate. Only the optimizer
stopping tolerance changes. This adapter writes a separate bound result.
"""
from pathlib import Path
import run

original_minimize = run.minimize
original_write = run.write

def minimize(*args, **kwargs):
    options = dict(kwargs['options'])
    assert options == dict(maxiter=200, gtol=1e-7)
    kwargs['options'] = dict(options, gtol=1e-5)
    return original_minimize(*args, **kwargs)

def write(path, value):
    assert Path(path).name == 'summary.json'
    value['numerical_repair'] = 'BFGS gtol1e-5 matches unchanged qualification threshold; no statistical model or validation-gate change'
    value['sources'][str(Path(__file__).resolve())] = run.digest(__file__)
    value['sources'][str(run.HERE/'summary.json')] = run.digest(run.HERE/'summary.json')
    original_write(run.HERE/'qualified-summary.json', value)

if __name__=='__main__':
    run.minimize = minimize
    run.write = write
    run.fit()
