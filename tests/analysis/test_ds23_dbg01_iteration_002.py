from run_ds23_dbg01_iteration_002 import configure, next_cases, RAW
from ds23_current_assignment_context import current_base_context
from types import SimpleNamespace
import numpy as np
import pytest


def test_next_batch_preserves_worst_order_and_closes_previous_cases():
    rows = [dict(case=f'DS23-{k:04}', policy='equal_assignment_priors',
                 arm=arm, policy_error_km=str(error))
            for k, error in [(81, 17.), (326, 14.), (35, 5.4), (41, 5.2), (111, 4.6)]
            for arm in ['c0', 'fitted_c']]
    assert next_cases(rows) == ['DS23-0035', 'DS23-0041']


def test_reused_stages_write_only_into_new_iteration_context():
    configure()
    import probe_ds23_worst_association_bottleneck as baseline
    import probe_ds23_single_curved_reentry as reentry
    import probe_ds23_support_aware_reentry as support
    import finalize_ds23_support_reentry as finalize
    import run_dbg01_latest_worst as dbg
    import audit_ds23_worst_iteration as audit
    assert baseline.OUT == dbg.PARENT == audit.OUT == RAW
    assert reentry.DEBUG == support.DEBUG == RAW
    assert reentry.OUT == support.NOMINATIONS == finalize.OLD == audit.REENTRY
    assert support.OUT == finalize.OUT == RAW/'support_aware_reentry'


def test_current_replacement_labels_drive_ablation_and_protected_support():
    def row(satellite):
        return dict(component='curve', candidate_index=satellite, candidate_norad=satellite)
    old = SimpleNamespace(rows=[row(1)], members=[0], slices=[slice(0, 2)])
    current = SimpleNamespace(rows=[row(2)], members=[0], slices=[slice(0, 2)], keep=np.ones(2, bool))
    data = dict(base=old, keep=np.ones(2, bool), node=dict(seed=dict(rows=[row(2)])))
    assert current_base_context(data, current)['base'].rows[0]['candidate_norad'] == 2
    assert old.rows[0]['candidate_norad'] == 1
    with pytest.raises(ValueError, match='current assignment labels'):
        current_base_context(dict(data, node=dict(seed=dict(rows=[row(1)]))), current)
    with pytest.raises(ValueError, match='measurement layout'):
        current_base_context(dict(data, keep=np.zeros(2, bool)), current)
