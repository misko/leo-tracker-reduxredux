"""Independent covariance densities for the new native-owner nomination inputs."""

from pathlib import Path
import numpy as np
import probe_ds23_native_augmented_family as study
from ds23_family_cavity import predictive_density_reference
from run_algo01_ds23_sample import read,write,sha


def main():
    assert read(study.OUT/'execution.json')['all_passed']
    path=study.OUT/'independent_nomination_audit.json'
    if path.exists():raise FileExistsError('preserve nomination audit')
    rows=[]
    for case in read(study.OUT/'protocol.json')['cases']:
        saved=read(study.OUT/(case+'.json'))
        if not saved['eligible']:continue
        data,_,_=study.parent(case);s=data['arms']['c0']
        data=dict(data,x=np.asarray(s['endpoint_east_north_km']),reference=np.asarray(s['phase_reference']))
        held=study.family_evidence(data,saved['target_index'])
        if held['held_ids']!=saved['held_IDs']:raise ValueError('held family membership changed')
        owners=[o for m in held['members'] for o in m['observation_ids']]
        if len(owners)!=len(set(owners)) or set(owners)!=set(held['held_ids']):raise ValueError('held family measurements duplicated')
        for row,sl in zip(data['base'].rows,data['base'].slices,strict=True):
            if row['candidate_index']==saved['target_index'] and np.any(held['calibration_mask'][sl]):raise ValueError('held family calibrated its nominee')
        for offer in saved['nominations']:
            captured=[];original=study.cavity.gaussian_prediction
            def record(raw,design,covariance,sigma):
                captured.append((raw.copy(),design.copy(),covariance.copy(),sigma.copy()))
                return original(raw,design,covariance,sigma)
            study.cavity.gaussian_prediction=record
            try:replay=study.cavity.candidate_prediction(data,held,offer['candidate_index'],offer['aliases'])
            finally:study.cavity.gaussian_prediction=original
            value,method=predictive_density_reference(*captured[-1]);delta=abs(value-offer['score'])
            if delta>2e-3 or abs(replay['score']-offer['score'])>1e-5:raise ValueError('native-family nomination density changed')
            rows.append(dict(case=case,norad=offer['norad'],predictive_density_difference=delta,method=method,
                score_replay_difference=replay['score']-offer['score'],all_held_IDs_distinct_and_excluded_from_calibration=True))
    write(path,dict(rows=rows,all_passed=True,no_new_position_fit_or_GPS=True,source_sha256=sha(Path(__file__))))


if __name__=='__main__':main()
