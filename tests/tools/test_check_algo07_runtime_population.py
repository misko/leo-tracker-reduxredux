import json

import numpy as np
import pytest
from check_algo07_runtime_population import compare_results


def test_population_comparison_requires_exact_tensors_and_calls(tmp_path):
    roots = [tmp_path/name for name in ('a', 'b')]
    for root in roots:
        root.mkdir()
        (root/'summary.json').write_text(json.dumps(dict(
            result=dict(associated={'c0': 4, 'fitted_c': 4}), seconds=1.)))
        (root/'call-00.json').write_text('{"objective": 4.0}')
        np.savez(root/'call-00.npz', raw=np.array([1., 2.]))
    assert compare_results(*roots)['checked_calls'] == 1
    np.savez(roots[1]/'call-00.npz', raw=np.array([1., 2.+1e-12]))
    with pytest.raises(AssertionError):
        compare_results(*roots)
    (roots[1]/'call-00.json').unlink()
    with pytest.raises(ValueError, match='inventories'):
        compare_results(*roots)
