"""Independent saved-control replay before any geographic evaluation."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

from matched_controls import HERE,digest,factor_contract,load_adapter,load_baseline,load_protocol,measurement_binding,read,write


def one(args):
    case,protocol_path=args
    from probe_ds23_graph_seeded_paths import build
    from probe_ds23_frequency_events import summary
    from debug_algo02_ds23_0268 import decomposition
    protocol,_=load_protocol(protocol_path)
    saved=read(HERE/'models'/protocol['model_id']/(case+'.json'))
    assert saved['protocol_sha256']==digest(protocol_path)
    d=load_baseline(case)
    assert d['baseline_sha256']==saved['baseline_sha256']
    binding=measurement_binding(d);module=load_adapter(protocol['adapter']['path']);arms={}
    for arm,old in saved.get('arms',{}).items():
        original=build(d,'default',arm,d['arms'][arm]['phase_reference'])
        p=module.build(d,arm,np.asarray(old['phase_reference']),case)
        assert factor_contract(p,d['entries'])==factor_contract(original,d['entries'])
        x=np.asarray(old['endpoint_east_north_km']);r=summary(p,x,d['entries']);c=p.calculate(x)
        gap=float(r['negative_twice_elbo']-old['negative_twice_elbo'])
        assert abs(gap)<1e-5 and abs(r['RMS_hz']-old['RMS_hz'])<1e-6
        for key in ('gates','linear_gates'):
            fresh=r[key]['tracks'] if key=='gates' else r[key]
            stored=old[key]['tracks'] if key=='gates' else old[key]
            assert [(g['component'],g['compatible']) for g in fresh]==[(g['component'],g['compatible']) for g in stored]
        terms=decomposition(p,x)
        assert r.get('linear_calibration_max_difference',0)<=1e-10
        arms[arm]=dict(objective_replay_difference=gap,RMS_replay_difference_hz=r['RMS_hz']-old['RMS_hz'],
            decomposition=terms,precision_iterations=c.get('precision_iterations'),
            final_log_precision_change=c.get('final_log_precision_change'),
            original_curved_gate_failures=[g['component'] for g in r['gates']['tracks'] if not g['compatible']],
            original_predictive_gate_failures=[g['component'] for g in r['linear_gates'] if not g['compatible']],
            original_phase_change_s=old['final_phase_change_s'])
    assert measurement_binding(d)==binding==saved['input_binding_sha256']
    return dict(case=case,arms=arms,policy_source=saved['policy_source'],passed=True)


def main(path,workers):
    protocol,_=load_protocol(path)
    with ProcessPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(one,[(c,path) for c in protocol['cases']]))
    arms=[v for r in rows for v in r['arms'].values()]
    result=dict(model_id=protocol['model_id'],passed=True,cases=len(rows),replayed_arms=len(arms),rows=rows,
        maximum_absolute_objective_replay_difference=max(abs(r['objective_replay_difference']) for r in arms),
        maximum_absolute_RMS_replay_difference_hz=max(abs(r['RMS_replay_difference_hz']) for r in arms),
        maximum_absolute_decomposition_error=max(abs(r['decomposition']['reconstruction_error']) for r in arms),
        maximum_final_log_precision_change=max(r['final_log_precision_change'] for r in arms if r['final_log_precision_change'] is not None),
        original_bindings_and_physical_factors_preserved=True,original_gate_results_replayed=True,
        predictive_calibration_feedback_zero=True,GPS_used=False,source_sha256=digest(Path(__file__)))
    write(HERE/'models'/protocol['model_id']/'independent_replay_audit.json',result)
    print({k:v for k,v in result.items() if k!='rows'},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();assert 1<=a.workers<=4;main(a.protocol,a.workers)
