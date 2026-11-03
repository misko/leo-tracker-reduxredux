"""Prior sigma1 baseline geometry, separate from matched new cone controls."""
import importlib.util,json
from dataclasses import replace
from pathlib import Path
import numpy as np
from mark import mark_arrays

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    from leo.contracts.regional_position import PositionScore
    oracle=module('prior_oracle',REPORTS/'2026_10_07_sigma1_root_cause/oracle.py');cone=module('prior_cone',HERE.parent/'cone_objective.py');theta,frames,support=cone.cone_bundle();output=dict(label='PRIOR sigma1 baseline, not matched new cone control',cases={})
    for case in ('1939','2139'):
        doc,old,obs,prior,bank,cp,prefix=oracle.load(case)
        path=REPORTS/('2026_10_07_sigma1_root_cause/shared_bias/results.json' if case=='1939' else '2026_10_07_sigma1_root_cause/boundary/results.json');receipt=json.loads(path.read_text());selected=list(receipt['selected'].values()) if case=='1939' else [r for r in receipt['selections'] if r['domain']=='expanded'];output['cases'][case]=dict(source_path=str(path),session_id=doc['session_id'],selections={})
        for r in selected:
            basin=r['basin'];a=cp.get(prefix+':'+basin+':association')['result'];c=cp.get(prefix+':'+basin+':calibration')['result'];sub=bank.select(a['selected_indices']);obj=cone.ConeObjective(obs,sub,prior,replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.),receiver_baseline_hz=np.asarray(c['receiver_baseline_hz']),strength=0.,theta=theta,frames=frames,support=support);v=np.asarray(r['vector']);value,_,terms=obj.evaluate(v);assert abs(value-r['objective'])<1e-6
            record=dict(basin=basin,objective=value,scenarios={})
            for scenario in ('candidate:fitted-time','reference-diagnostic:receive-time'):
                trial=v.copy()
                if scenario.startswith('reference'):trial[:2]=oracle.reference_point(prior,doc['reference_latitude_deg'],doc['reference_longitude_deg']);trial[7:]=0
                unit=cone.directions(sub,obs,prior,trial,obj.basis,derivatives=False)[0];rows=mark_arrays(unit,sub.numbers,obs.receiver,terms.responsibilities,theta,frames,scenario);mass=sum(row['signal_mass'] for row in rows);names=('opposite_east_west','behind_nominal_boresight','outside_empirical_ellipse','nearer_other_receiver_axis','below_horizon')
                record['scenarios'][scenario]=dict(signal_mass=mass,fractions={name:sum(row[name+'_mass'] for row in rows)/mass for name in names},top3={name:sorted((row for row in rows if row['signal_mass']>=10 and row[name+'_fraction']>.5),key=lambda row:row[name+'_mass'],reverse=True)[:3] for name in names},all_satellite_receiver_rows=rows)
            output['cases'][case]['selections'][r['arm']]=record
        (HERE/'prior_flags.json').write_text(json.dumps(output,indent=2));print(case,json.dumps({a:{s:d['fractions'] for s,d in r['scenarios'].items()} for a,r in output['cases'][case]['selections'].items()}),flush=True)

if __name__=='__main__':main()
