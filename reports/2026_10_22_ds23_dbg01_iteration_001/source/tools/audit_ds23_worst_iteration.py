"""Independent density and exact gate replay for this bounded DBG01 iteration."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

import audit_ds23_family_cavity as auditor
import probe_ds23_family_cavity_nominations as nomination
import run_dbg01_latest_worst as study
from ds23_family_cavity import predictive_density_reference
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay
from probe_ds23_single_curved_reentry import OUT as REENTRY, predictive_track_data
from probe_ds23_worst_association_bottleneck import OUT, setup, build
from run_algo01_ds23_sample import ROOT, read, sha, write


def endpoint(job):
    case, kind, index = job
    out = study.configure(case)
    d = study.data(case)
    if kind == 'audit':
        source = out/'audit.json'
        r = read(source)
        records = [(name+'_'+arm, v[name], d['node'], d['keep'], d['entries'], 'baseline')
                   for arm, v in r['arms'].items() for name in ['endpoint', 'diagnostic_point']]
    else:
        source = out/f'{kind}_{index:02d}.json'
        r = read(source)
        mask, entries = d['keep'].copy(), d['entries']
        control = r['target'] if kind == 'prior' else 'baseline'
        if kind == 'family':
            for row, sl in zip(d['base'].rows, d['base'].slices, strict=True):
                if row['candidate_norad'] == r['target']:
                    mask[sl] = False
            entries = [e for e in entries if e['norad'] != r['target']]
        elif kind == 'track':
            for row, sl in zip(d['base'].rows, d['base'].slices, strict=True):
                if row['component'] == r['target']:
                    mask[sl] = False
        nodes = read(out/'hypothesis_bank.json')['nodes'] if kind == 'restart' else None
        records = [(arm, saved, nodes[saved['final_mode']] if nodes else d['node'], mask, entries, control)
                   for arm, saved in r['arms'].items()]
    checks = []
    for name, saved, node, mask, entries, control in records:
        arm = 'fitted_c' if 'fitted_c' in name else 'c0'
        p = study.engine.build(node, mask, arm, np.asarray(saved['phase_reference']), entries, control)
        x = np.asarray(saved['endpoint_east_north_km'])
        c = p.calculate(x)
        delta = abs(c['negative_twice_elbo']-saved['negative_twice_elbo'])
        if delta > 1e-5:
            raise ValueError('DBG01 endpoint objective changed')
        replay = study.engine.summary(p, x, entries)
        assert_curved_gate_replay(saved['gates'], replay['gates'])
        assert_curved_gate_replay(saved['linear_gates'], replay['linear_gates'])
        labels = sorted({row['candidate_index'] for row in node['seed']['rows']})
        means = d['all_means'][labels].copy()
        if control == 'phase_zero_mean':
            means *= 0
        dd = dict(d, keep=mask)
        direct = auditor.density(dd, p, x, means, entries)
        checks.append(dict(arm=name, endpoint_objective_difference=delta, **direct))
    return dict(case=case, kind=kind, index=index, checks=checks, all_passed=True, source_sha256=sha(source))


def nominations(case):
    d = setup(case)
    saved = read(REENTRY/(case+'_nominations.json'))
    x = np.asarray(d['arms']['c0']['endpoint_east_north_km'])
    d['x'] = x
    p = build(d, 'c0', d['arms']['c0']['phase_reference'])
    checks = []
    for row in saved['targets']:
        data = predictive_track_data(d, p, x, row['row_index'])
        for candidate in row['candidates']:
            capture = []
            original = nomination.gaussian_prediction
            def record(raw, design, covariance, sigma):
                capture.append((raw.copy(), design.copy(), covariance.copy(), sigma.copy()))
                return original(raw, design, covariance, sigma)
            nomination.gaussian_prediction = record
            try:
                replay = nomination.candidate_prediction(d, data, candidate['candidate_index'], candidate['aliases'])
            finally:
                nomination.gaussian_prediction = original
            replay_delta = abs(replay['score']-candidate['score'])
            direct, method = predictive_density_reference(*capture[-1])
            delta = abs(direct-candidate['score'])
            if replay_delta > 1e-5 or delta > 2e-3:
                raise ValueError('new-curve predictive density failed independent audit')
            checks.append(dict(component=row['target']['component'], norad=candidate['norad'],
                               replay_difference=replay_delta, density_difference=delta, method=method))
    return dict(case=case, checks=checks, all_passed=True,
                source_sha256=sha(REENTRY/(case+'_nominations.json')))


def main():
    execution = read(OUT/'DBG01_analysis_execution.json')
    assert execution['all_terminal'] and execution['all_passed']
    cases = read(OUT/'protocol.json')['cases']
    jobs = []
    for case in cases:
        interventions = read(OUT/case/'DBG01/interventions.json')
        jobs += [(case, 'audit', 0)]+[(case, 'restart', i) for i in range(81)]
        jobs += [(case, kind, i) for kind in ['family', 'track', 'prior']
                 for i in range(len(interventions[kind]))]
    results = []
    with ProcessPoolExecutor(max_workers=12) as pool:
        for f in as_completed([pool.submit(endpoint, j) for j in jobs]):
            results.append(f.result())
    nominees = [nominations(case) for case in cases]
    write(OUT/'independent_iteration_audit.json', dict(all_passed=True, rows=results, nominations=nominees,
          endpoint_arms=sum(len(r['checks']) for r in results),
          nomination_candidates=sum(len(r['checks']) for r in nominees),
          all_restart_family_track_prior_endpoints_checked=True,
          grid_coordinates_and_model_are_recorded_but_not_independently_reintegrated_at_every_pixel=True,
          source_sha256=sha(Path(__file__))))
    print('Independent audit passed', sum(len(r['checks']) for r in results), 'endpoint arms;',
          sum(len(r['checks']) for r in nominees), 'candidate densities', flush=True)


if __name__ == '__main__':
    main()
