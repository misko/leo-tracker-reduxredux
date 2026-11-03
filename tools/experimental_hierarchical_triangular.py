"""Research-only triangular solve experiment; exact replay must qualify any use."""

import inspect

import dsx01_hierarchical_bound as baseline
from scipy.linalg import solve_triangular

# Derive only the solver substitution from the current implementation so all
# priors, stopping criteria, iterations and output fields remain identical.
source = inspect.getsource(baseline.hierarchical_bound)
old_mean = 'np.linalg.solve(root.T, np.linalg.solve(root, rhs))'
old_inverse = 'np.linalg.solve(root, identity)'
if source.count(old_mean) != 1 or source.count(old_inverse) != 1:
    raise ValueError('Unexpected experimental solver source')
source = source.replace(old_mean, 'solve_triangular(root.T, solve_triangular('
                        'root, rhs, lower=True, check_finite=False), check_finite=False)')
source = source.replace(old_inverse, 'solve_triangular(root, identity, lower=True, '
                        'check_finite=False)')
namespace = dict(vars(baseline), solve_triangular=solve_triangular)
exec(compile(source, __file__, 'exec'), namespace)
hierarchical_bound = namespace['hierarchical_bound']
