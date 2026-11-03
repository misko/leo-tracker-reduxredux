import numpy as np

from ds23_joint_component_rf import JointComponentWorkspace
from ds23_rf_carrier_alias_grid import AliasBranchWorkspace
from inventory_ds23_paired_component_cycles import PERIOD


def test_training_RF_likelihood_recovers_injected_carrier_alias_branch():
    segments = [np.arange(a, a+1200) for a in [250, 3650, 7050, 10450, 13850]]
    args = (2500000., 'lower', [23.2, 193.4], segments)
    base = JointComponentWorkspace(np.zeros(20000, complex), *args)
    truth = np.array([12000.+PERIOD, .123, 6.4, 42000., -.234, -3.3])
    columns = base.columns(truth)
    y = np.zeros_like(base.y)
    for k, ix in enumerate(segments):
        y[ix] = columns[ix]@np.array([1+2j, -2+.8j])*np.exp(.3j*k)+(k+1j)
    seeds = [dict(CFO_hz=12000., offset_samples=.123, modulation_ppm=6.4),
        dict(CFO_hz=42000., offset_samples=-.234, modulation_ppm=-3.3)]
    fitted = AliasBranchWorkspace(y, *args).joint_fit(seeds)
    assert list(fitted['selected_pilot_aliases']) == [1, 0]
    assert fitted['trained_branches'] == 9
    assert fitted['score'] > 1-1e-8
    np.testing.assert_allclose(fitted['parameters'][::3], truth[::3], atol=.1, rtol=0)
    used = np.zeros(len(y), bool)
    used[np.concatenate(segments)] = True
    changed = y.copy()
    changed[~used] = 1e6+2e6j
    counterfactual = AliasBranchWorkspace(changed, *args).joint_fit(seeds)
    np.testing.assert_array_equal(counterfactual['parameters'], fitted['parameters'])
    np.testing.assert_array_equal([r['training_score'] for r in counterfactual['branch_scores']],
        [r['training_score'] for r in fitted['branch_scores']])
