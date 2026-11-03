"""Correct innovation-screen units at saved endpoints; no position refits."""

import copy
from pathlib import Path

import numpy as np

import repair_ds23_iteration009_targets as repair
from ds23_target_radio_covariance import make_target_problem,retained_covariance_metrics
from run_ds23_combined_recovery_full import valid
from evaluate_ds23_phase_refreshed import extend_associations
from dbg01_unassociated import ownership
from run_algo01_ds23_sample import read,write,sha

SOURCE=repair.runner.RAW/'target_radio_covariance'
OUT=repair.runner.RAW/'target_radio_covariance_v2'


def main():
    repair.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve innovation-unit audit')
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),helper_sha256=sha(Path(make_target_problem.__code__.co_filename)),
        original_inference_protocol_sha256=sha(SOURCE/'protocol.json'),
        correction='dimensionless whitened innovations mapped to75Hz before existing screen, equivalent normalized noise floor1',
        original_positions_phases_kernels_scales_and_data_unchanged_no_refit=True,
        v1_screen_statistics_not_used_for_any_accepted_algorithm=True,
        v1_source_preserved_in_original_experiment_source_v1=True))
    rows=[]
    for path in sorted(SOURCE.glob('DS23*.json')):
        old=read(path);result=copy.deepcopy(old);d=repair.engine.current_setup(old['case']);d=dict(d,keep=np.asarray(old['mask'],bool));model=old['covariance'];checks=[]
        for arm,saved in old['arms'].items():
            p=make_target_problem(d,arm,saved['phase_reference'],old['component'],model['alpha'],model['tau_s'],old['noise_scale'])
            x=np.asarray(saved['endpoint_east_north_km']);delta=p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
            if abs(delta)>1e-5:raise ValueError('unit correction changed scientific inference objective')
            gates=retained_covariance_metrics(p,x);result['arms'][arm]['gates']=gates
            extended=extend_associations(p,x,gates);lookup={t['key']:t for t in d['scan'].tracks}
            accepted=[dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids'])) for r in extended['tracks']]
            ids=ownership(accepted)
            result['coverage'][arm].update(associated=len(ids),percent=100*len(ids)/len(d['observations']),
                associated_tracks=sum(r['compatible'] for r in accepted),accepted_observation_ids=sorted(ids),associations=extended)
            checks.append(dict(arm=arm,original_objective_difference=delta))
        result.update(paired_valid=bool(valid(result['arms'])),innovation_units_corrected_without_refit=True,
            original_result_sha256=sha(path),unit_audit=checks)
        write(OUT/path.name,result);rows.append(dict(case=old['case'],method=old['method'],paired_valid=result['paired_valid']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
