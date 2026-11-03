"""Four native predictor calls separate saved timing and geography changes."""

import importlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT/'reports/2026_10_16_dsx01_models'
PREVIOUS = ROOT/'reports/2026_10_16_dsx01_iteration2'
sys.path.insert(0, str(OLD))
common = importlib.import_module('common')


def run(label):
    from leo.analysis.hard60_score import predict_orbits
    from leo.analysis.regional_position_score import zero_sum_basis

    ctx = common.load_context(label)
    a = json.loads((PREVIOUS/'results'/f'{label}-fitted-c-profile.json').read_text())
    b = json.loads((PREVIOUS/'expanded-results'/f'{label}-fitted-c-profile.json').read_text())
    before = np.load(PREVIOUS/'results'/f'{label}-fitted-c-profile.npz')
    after = np.load(PREVIOUS/'expanded-results'/f'{label}-fitted-c-profile.npz')
    av, bv = np.array(a['vector']), np.array(b['vector'])
    at = av[7]+ctx.model.basis@av[8:]
    numbers = b['bank_transport']['expanded_numbers']
    expanded_tau = bv[7]+zero_sum_basis(len(numbers))@bv[8:]
    bt = np.array([expanded_tau[numbers.index(int(n))] for n in ctx.bank.numbers])
    predictions = {}
    for name, xy, tau in (('aa', av[:2], at), ('ab', av[:2], bt),
                          ('ba', bv[:2], at), ('bb', bv[:2], bt)):
        predictions[name] = predict_orbits(ctx.bank, ctx.observations, ctx.prior,
                                           xy, tau, derivatives=False)[0]
    timing = .5*((predictions['ab']-predictions['aa'])+
                 (predictions['bb']-predictions['ba']))
    geography = .5*((predictions['ba']-predictions['aa'])+
                    (predictions['bb']-predictions['ab']))
    np.testing.assert_allclose(timing+geography, predictions['bb']-predictions['aa'], atol=1e-10)
    lookup = {int(n): i for i, n in enumerate(ctx.bank.numbers)}
    candidate = np.array([lookup[int(n)] for n in before['satellite_number']])
    rows = np.arange(len(candidate))
    lost = before['associated'] & ~after['associated']
    output = dict(source_id=label, native_predictor_calls=4, source_replay_objectives=2,
        localization_fits=0, geographic_movement_km=float(np.linalg.norm(av[:2]-bv[:2])),
        decomposition='symmetric two-order/Shapley orbit prediction split, original same candidate',
        lost=int(lost.sum()), contributions={})
    for name, value in (('timing', timing), ('geography', geography)):
        residual = value[rows, candidate][lost]
        output['contributions'][name] = dict(
            absolute_quantiles=np.quantile(abs(residual), [0, .1, .5, .9, 1]).tolist(),
            rms_hz=float(np.sqrt(np.mean(residual**2))))
    common.save_json(HERE/f'orbit_split_{label}.json', output)
    print(label, output['contributions'], flush=True)


if __name__ == '__main__':
    for label in sys.argv[1:]:
        run(label)
