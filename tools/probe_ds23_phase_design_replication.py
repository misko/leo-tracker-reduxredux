"""Replicate timing-information diagnostics with matched independent noise.

The radio simulation remains fixed. Two additional timing-noise draws test
whether the apparent benefit depended on the first hypothetical measurements.
These are repeated measurements on 20 templates, not 40 independent scans.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_phase_measurement_design import choose_labels
from probe_ds23_phase_measurement_design import OUT as DESIGN_OUT,BULK as DESIGN_BULK,refit
from probe_ds23_synthetic_known_nuisance import setup
from probe_ds23_synthetic_noise import gate_counts
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=DESIGN_OUT/'noise_replication'
BULK=Path('/srv/bulk/leo/research/ds23-phase-design-replication-20261021')
SETTINGS={'six_sd01':dict(budget=6,sigma_s=.1),'three_sd002':dict(budget=3,sigma_s=.02)}
METHODS=('information','point_count','random')
DRAWS=(1,2)


def one(case):
    protocol=read(OUT/'protocol.json');began=time.monotonic();rows=[]
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300second timing-noise replication cap')))
    signal.alarm(300)
    try:
        design_path=DESIGN_BULK/(case+'_design.json');design=read(design_path)
        assert design['no_truth_or_simulation_outcome_used']
        selections={}
        for setting,s in SETTINGS.items():
            selections[setting]={m:choose_labels(design['design'],s['sigma_s'],s['budget'],m,
                831017+int(case.split('-')[1])) for m in METHODS}
        # Commit the selection before reading either simulated phase truth or noise.
        selection_path=BULK/(case+'_selection.json')
        selection=dict(case=case,selections=selections,design_sha256=sha(design_path))
        if selection_path.exists() and read(selection_path)!=selection:raise ValueError('replication selection changed')
        if not selection_path.exists():write(selection_path,selection)
        scan,node,mask,powers,means,hyper,entries,truth,baseline=setup(case,protocol['site_by_case'][case])
        for draw in DRAWS:
            noise=np.random.default_rng(194819+1009*draw+int(case.split('-')[1])).normal(size=len(means))
            for setting,s in SETTINGS.items():
                for method in METHODS:
                    path=BULK/f'{case}_{setting}_{method}_draw{draw}.json'
                    if path.exists():rows.append(read(path));continue
                    ids=selections[setting][method]['label_indices']
                    measurements=[dict(candidate_index=design['labels'][k],norad=design['norads'][k],
                        phase_s=truth['true_phases_s'][k]+s['sigma_s']*noise[k],sigma_s=s['sigma_s']) for k in ids]
                    pair={a:refit(scan,node,mask,a,powers,means,hyper,entries,measurements) for a in ARMS}
                    for r in pair.values():
                        r['synthetic_position_error_km']=float(np.linalg.norm(np.array(r['endpoint_east_north_km'])-protocol['site_by_case'][case]))
                        r['original_gate_counts']=gate_counts(r);assert r['linear_calibration_max_difference']==0
                    result=dict(case=case,setting=setting,method=method,draw=draw,status='complete',arms=pair,
                        paired_qualified=valid(pair),measurements=measurements,selection_sha256=sha(selection_path),
                        real_DS23_accuracy_gain=False)
                    write(path,result);rows.append(result)
                    print(case,setting,method,draw,result['paired_qualified'],flush=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();write(BULK/(case+'_execution_failure.json'),dict(case=case,error=repr(exc)))
    finally:signal.alarm(0)
    return dict(case=case,completed=len(rows),total=len(SETTINGS)*len(METHODS)*len(DRAWS),seconds=time.monotonic()-began)


def main():
    base=read(DESIGN_OUT/'protocol.json');OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    protocol=dict(cases=base['cases'],site_by_case=base['site_by_case'],settings=SETTINGS,methods=METHODS,draws=DRAWS,
        source_design_protocol_sha256=sha(DESIGN_OUT/'protocol.json'),
        matched_measurement_count_precision_and_normal_draws=True,selection_fixed_before_phase_truth_and_noise=True,
        matched_c0_fitted_c=True,workers=8,per_case_seconds=300,cold_start=[0,0],region_km=25,
        phase_rounds=5,position_steps=48,original_RF_priors_gates_and_observations_unchanged=True,
        repeated_noise_on_same20templates_not_new_independent_scans=True,real_DS23_accuracy_gain=False,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_gaussian_information.py',
            ROOT/'tools/ds23_phase_measurement_design.py',ROOT/'tools/probe_ds23_phase_measurement_design.py']})
    import json
    protocol=json.loads(json.dumps(protocol));path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('timing-noise replication protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=8) as pool:
        execution=[f.result() for f in as_completed([pool.submit(one,c) for c in protocol['cases']])]
    write(OUT/'execution.json',dict(rows=execution,all_terminal=True,
        all_instances_complete=all(r['completed']==r['total'] for r in execution)))


if __name__=='__main__':main()
