"""Independent saved-IQ score/covariance replay and carrier-epoch checks."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import copy
import json
import numpy as np

from ds23_joint_component_refinement import JointComponentWorkspace
from ds23_differential_rf_epoch import frequency_rate_response,inject_component_rates
from select_ds23_differential_information import OUT,BULK
from run_algo01_ds23_sample import read,write,sha


def reconstruct(record):
    job=record['job'];case=record['case']
    with np.load(BULK/'panels'/(case+'.npz'),allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata_json']));point=next(r for r in metadata['points'] if r['probe']==record['probe'])
        v=z[point['window_key']][:,point['receiver_offset']]
    y=v[:,0].astype(float)+1j*v[:,1].astype(float)
    seeds=[dict(CFO_hz=job[k]['cfo_hz'],offset_samples=0.,modulation_ppm=0.) for k in ['first','second']]
    p=JointComponentWorkspace(y,metadata['sample_rate_hz'],job['edge'],[job[k]['epoch'] for k in ['first','second']],seeds)
    p.segments=[np.array(ix,int) for ix in record['segments']]
    return p


def one(record):
    if record['status']!='complete':return dict(case=record['case'],probe=record['probe'],status='failed_source')
    p=reconstruct(record);maximum=0.;score_difference=0.;covariance_difference=0.;count=0
    cases=[(record['full'],None,None)]+[(r['fit'],i,None) for i,r in enumerate(record['folds'])]
    cases += [(r['fit'],i,None) for i,f in enumerate(record['folds']) for r in f['alternative_carriers']]
    cases += [(r,None,r['frames']) for r in record['bootstrap_replicates']]
    original=p.segments
    for saved,parity,draws in cases:
        p.segments=original if draws is None else [original[k] for k in draws]
        s=p.statistics(saved['parameters'],parity,derivatives=True)
        noise=s['squared_error']/max(1,s['samples']-17*len(p.segments)-6)
        standardized=float(np.max(abs(s['rhs'])/np.sqrt(np.maximum(np.diag(s['normal'])*noise/2,1e-20))))
        score_difference=max(score_difference,abs(standardized-saved['maximum_standardized_score']))
        if 'full_covariance' in saved:
            covariance=np.diag(p.scale)@np.linalg.solve(s['normal'],np.eye(6))@np.diag(p.scale)*noise/2
            covariance_difference=max(covariance_difference,float(np.max(abs(covariance-saved['full_covariance']))))
        if 'score' in saved:maximum=max(maximum,abs(s['score']-saved['score']))
        if draws is None and parity is not None:
            predicted=p.statistics(saved['parameters'],parity,derivatives=False,prediction=True)
            assert predicted['heldout_samples']>0
        count+=1
    assert maximum<1e-12 and score_difference<1e-8 and covariance_difference<1e-5;p.segments=original
    response=frequency_rate_response(p,record['full']['parameters']);injections=[]
    if record['RF_qualified']:
        for component in [0,1]:
            values=[]
            for sign in [-1,1]:
                rates=np.zeros(2);rates[component]=sign*1000.
                view=copy.copy(p);view.y=inject_component_rates(p,record['full']['parameters'],rates)
                view.start=np.asarray(record['full']['parameters']);fitted=view.optimize(iterations=48)
                values.append(float(np.array([1.,0.,0.,-1.,0.,0.])@fitted['parameters']))
            measured=(values[1]-values[0])/2;expected=response[component]*1000.
            injections.append(dict(component=component,expected_shift_hz=expected,measured_shift_hz=measured,
                difference_hz=measured-expected))
    result=dict(case=record['case'],probe=record['probe'],RF_qualified=record['RF_qualified'],replayed_fits=count,
        maximum_RF_score_difference=maximum,maximum_stationarity_score_difference=score_difference,
        maximum_covariance_replay_difference=covariance_difference,
        frequency_rate_response_s=response,shared_receiver_rate_response_s=float(response.sum()),
        injected_frequency_rate_checks=injections,
        epoch_linearization_qualified=all(abs(r['difference_hz'])<=.3 for r in injections),
        source_sha256=sha(BULK/f"{record['case']}_probe{record['probe']:06d}_RF.json"))
    print(record['case'],record['probe'],result['epoch_linearization_qualified'],response,flush=True);return result


def main():
    source=read(OUT/'RF_pilot.json');exports=read(OUT/'RF_export.json')
    for r in exports['receipts']:assert sha(BULK/'panels'/(r['case']+'.npz'))==r['sha256']
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,r) for r in source['rows']])]
    write(OUT/'RF_independent_audit.json',dict(rows=rows,all_terminal=True,source_RF_sha256=sha(OUT/'RF_pilot.json'),
        native_RF_and_whole_frame_bootstrap_replayed=True,conditional_uncertainty_not_absolute_error_coverage=True,
        position_inference_not_performed=True))


if __name__=='__main__':main()
