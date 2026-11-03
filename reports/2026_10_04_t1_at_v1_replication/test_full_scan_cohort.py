import json
from types import SimpleNamespace

import numpy as np
import pytest

from full_scan_cohort import association_root, validate_fit_scope, digest


@pytest.mark.parametrize('attempt,scan', [('attempt2', 'N01'), ('remaining', 'N12')])
def test_resolve_original_association_from_its_receipt(tmp_path, attempt, scan):
    path = tmp_path/attempt/scan/'fitted-c.json'
    path.parent.mkdir(parents=True); path.write_text(json.dumps({'scan': scan}))
    meta = dict(association_source=str(path), association_sha256=digest(path))
    assert association_root(meta, scan) == tmp_path/attempt
    with pytest.raises(ValueError): association_root(meta, 'N99')
    path.write_text('{}')
    with pytest.raises(ValueError): association_root(meta, scan)


def test_all_assigned_windows_and_both_rf_arms_required():
    data = SimpleNamespace(original_rows=np.array([2, 5, 9]), numbers=np.array([123, 456]))
    record = dict(fit_original_rows=[2, 5, 9], evaluation_original_rows=[2, 5, 9],
                  heldout_original_rows=[], input_metadata={'numbers': [123, 456]},
                  arms={'fitted-c': {}, 'zero-c': {}})
    validate_fit_scope(record, data)
    with pytest.raises(ValueError): validate_fit_scope(dict(record, fit_original_rows=[2, 5]), data)
    with pytest.raises(ValueError): validate_fit_scope(dict(record, heldout_original_rows=[9]), data)
    with pytest.raises(ValueError): validate_fit_scope(dict(record, arms={'fitted-c': {}}), data)
