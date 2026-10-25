"""Read sealed identity outputs only; no orbit propagation or score refit."""
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / 'identity'
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    seal = read(ROOT/'RF_seal.json')
    for name, digest in seal['files'].items():
        assert sha(ROOT/name) == digest, name
    protocol = read(ROOT/'protocol.json')
    assert seal['protocol_sha256'] == sha(ROOT/'protocol.json')
    for path,digest in protocol['source_hashes'].items():
        assert sha(Path(path)) == digest, path
    preflight = read(ROOT/'independent_preflight.json')
    for key in ('previous_transfer_inputs_verified','frozen_scan_inputs_verified'):
        for path,digest in preflight[key].items():
            assert sha(Path(path)) == digest, path
    execution = read(ROOT/'execution.json')
    assert execution['cumulative_scientific_seconds'] <= 600
    assert len(execution['rows']) == 8 and all(r['status']=='complete' for r in execution['rows'])
    scores = 0
    adaptive = 0
    maximum_score_error = 0.
    maximum_adaptive_error = 0.
    minimum_elevation = float('inf')
    maximum_prior_mass_error = 0.
    null_alias_stable = 0
    physical_alias_stable = 0
    ranking = []
    for case in protocol['cases']:
        screen = read(ROOT/(case+'_screen.json'))
        parent = read(SOURCE/'family_cavity/position'/(case+'.json'))
        node = parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
        tracks = {r['key']:r for r in read(SOURCE/case/'tracks.json')}
        pools = set(screen['candidate_indices'])
        forbidden = {oid for row in node['seed']['rows'] if row['candidate_index'] in pools
                     for oid in tracks[row['component']]['observation_ids']}
        for arm in ('c0','fitted_c'):
            result = read(ROOT/(case+'_'+arm+'_result.json'))
            cavity = result['cavity']
            assert not forbidden.intersection(cavity['calibration_ids'])
            assert not forbidden.intersection(cavity['predictive_ids'])
            for flag in ('phase_qualified','precision_qualified','support_qualified','original_remaining_gates_pass'):
                assert cavity[flag]
            assert cavity['maximum_unclipped_parent_phase_s'] <= 15.000001
            assert cavity['final_log_precision_change'] <= 1e-5
            assert not result['identity_qualified'] and not result['GPS_used'] and result['position_fits']==0
            single = result['panels'][0]
            singles = {r['norad']:r for r in single['candidates']}
            for panel in result['panels']:
                null = panel['null']
                null_alias_stable += null['alias_stable']
                assert set(r['norad'] for r in panel['candidates']) == set(screen['candidate_norads'])
                ids = [oid for owner in panel['entries'] for oid in owner['observation_ids']]
                assert len(ids) == len(set(ids))
                assert abs(sum(np.ravel(null['allowed_alias_posterior']))-1) < 1e-10
                for row in panel['candidates']:
                    scores += 1
                    assert row['status']=='complete' and row['numerically_qualified']
                    assert not row['identity_qualified']
                    assert abs(sum(np.ravel(row['allowed_alias_posterior']))-1) < 1e-10
                    error = abs(row['objective']-row['reference_objective'])
                    assert abs(error-row['score_error']) < 1e-12 and error <= 1e-3
                    maximum_score_error = max(maximum_score_error,error,row.get('conditional_score_error',0))
                    maximum_prior_mass_error = max(maximum_prior_mass_error,abs(row['quadrature_prior_mass']-1))
                    minimum_elevation = min(minimum_elevation,row['minimum_elevation_deg'])
                    physical_alias_stable += row['alias_stable']
                    assert abs(row['gain_vs_unresolved_curve']-(null['objective']-row['objective'])) < 1e-10
                    if 'conditional_objective' in row:
                        assert abs(row['discovery_objective']-singles[row['norad']]['objective']) < 1e-8
                        assert abs(row['conditional_objective']-row['objective']+row['discovery_objective']) < 1e-8
                        assert abs(null['conditional_objective']-null['objective']+single['null']['objective']) < 1e-8
                        assert abs(row['held_gain_vs_unresolved_curve']-null['conditional_objective']+row['conditional_objective']) < 1e-8
                    if 'adaptive_reference' in row:
                        adaptive += 1
                        error = abs(row['objective']-row['adaptive_reference']['objective'])
                        if 'adaptive_discovery_reference' in row:
                            ref = row['adaptive_reference']['objective']-row['adaptive_discovery_reference']['objective']
                            error = max(error,abs(row['conditional_objective']-ref))
                        assert error <= 1e-3
                        maximum_adaptive_error = max(maximum_adaptive_error,error)
                key = 'conditional_objective' if panel['panel']!='single' else 'objective'
                ordered = sorted(panel['candidates'],key=lambda r:(r[key],r['norad']))
                ranking.append(dict(case=case,arm=arm,panel=panel['panel'],winner=ordered[0]['norad'],
                    runner_up=ordered[1]['norad'],runner_up_gap=ordered[1][key]-ordered[0][key]))
    assert scores == 112 and adaptive == 22
    output = dict(all_passed=True,RF_seal_sha256=sha(ROOT/'RF_seal.json'),protocol_sha256=sha(ROOT/'protocol.json'),
        sealed_file_hashes_verified=len(seal['files']),job_arms=8,candidate_contexts=scores,adaptive_references=adaptive,
        maximum_1281_2561_score_discrepancy=maximum_score_error,maximum_adaptive_score_discrepancy=maximum_adaptive_error,
        minimum_visibility_deg=minimum_elevation,maximum_quadrature_prior_mass_error=maximum_prior_mass_error,
        alias_stable_physical_contexts=physical_alias_stable,alias_stable_null_contexts=null_alias_stable,
        union_cavity_native_ID_exclusion_verified=True,all_remaining_legacy_gates_pass=True,
        held_owner_joint_minus_discovery_and_null_gains_verified=True,
        ranking=ranking,scientific_wall_seconds=execution['cumulative_scientific_seconds'],
        real_GPS_used=False,position_fits=0,new_propagation=False,identity_qualification=False,
        source_sha256=sha(Path(__file__)))
    with (HERE/'identity_terminal_audit.json').open('x') as handle:
        json.dump(output,handle,indent=2);handle.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k!='ranking'},indent=2))


if __name__ == '__main__':
    main()
