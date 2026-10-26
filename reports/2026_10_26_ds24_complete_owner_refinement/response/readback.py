"""Posthoc frozen-Gaussian response of saved native CFO deltas; no RF/fit."""
import time
STARTED=time.monotonic()
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=Path('/srv/bulk/leo/research/ds24-detector-response-r01/influence')
spec=importlib.util.spec_from_file_location('frozen_bias_basis',OLD/'local_math.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)


def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):
    with Path(p).open('x')as f:json.dump(x,f,indent=2,allow_nan=False);f.write('\n')
def table(p,rows):
    with Path(p).open('x',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def decompose(delta,times,q):
    basis=prior.bias_basis(times,q)
    projected=basis@np.linalg.lstsq(basis,np.asarray(delta,float),rcond=None)[0]
    rest=np.asarray(delta,float)-projected
    if not np.allclose(basis.T@rest,0,atol=1e-8,rtol=0):raise ValueError('projection not orthogonal')
    return projected,rest


class Fixtures(unittest.TestCase):
    def test_projection_and_linear_additivity(self):
        t=np.linspace(0,1,17);q=np.full(17,1.1)
        delta=2+t+3*t*t+np.sin(t*23)
        smooth,rest=decompose(delta,t,q)
        h=np.arange(34,dtype=float).reshape(2,17)/30
        np.testing.assert_allclose(h@delta,h@smooth+h@rest,rtol=1e-13,atol=1e-13)
        np.testing.assert_allclose(decompose(smooth,t,q)[1],0,atol=1e-13)

    def test_native_delta_is_not_multiplied_by_q(self):
        delta=np.full(10,7.)
        smooth,rest=decompose(delta,np.arange(10),np.full(10,1.2))
        np.testing.assert_allclose(smooth,delta,atol=1e-13)
        np.testing.assert_allclose(rest,0,atol=1e-13)


def main():
    if(HERE/'seal.json').exists():raise FileExistsError('single posthoc readback only')
    began=time.monotonic()
    tests=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Fixtures))
    if not tests.wasSuccessful():raise RuntimeError('projection fixtures failed')
    test_seconds=time.monotonic()-began
    for seal in (ROOT/'measurement/RF_seal.json',ROOT/'position/RF_seal.json'):
        for p,h in load(seal)['files'].items():
            if sha(p)!=h:raise ValueError('sealed input changed: '+p)
    arrays=np.load(OLD/'response_arrays.npz')
    ledger={r['case']:r for r in load(OLD/'complete_owner_ledger.json')}
    correction=load(ROOT/'measurement/corrections.json')
    assert correction['coverage_complete']and len(correction['rows'])==159
    endpoints=load(ROOT/'position/execution.json')['all8_slots']
    owner_rows=[];case_rows=[];ordering=[];checks=[]
    for case in ('DS24-0010','DS24-0011'):
        native=ledger[case]['ordered_rows'];ids=[r['observation_id']for r in native]
        assert len(ids)==len(set(ids))
        index={oid:i for i,oid in enumerate(ids)}
        selected=[r for r in correction['rows']if r['case']==case]
        delta=np.zeros(len(native));smooth=np.zeros(len(native));rest=np.zeros(len(native))
        owners=[]
        for owner in sorted({r['complete_owner']for r in selected}):
            rr=sorted([r for r in selected if r['complete_owner']==owner],key=lambda r:(r['time_s'],r['native_observation_id']))
            ix=np.array([index[r['native_observation_id']]for r in rr])
            assert all(native[i]['owner']==owner for i in ix)
            values=np.array([r['corrected_cfo_hz']-r['original_cfo_hz']for r in rr])
            p,e=decompose(values,[native[i]['time_s']for i in ix],[native[i]['q']for i in ix])
            delta[ix]=values;smooth[ix]=p;rest[ix]=e
            owners.append((owner,rr[0]['role'],ix,values,p,e))
            for j,i in enumerate(ix):ordering.append(dict(case=case,native_id=ids[i],saved_response_column=int(i),owner=owner,
                native_delta_hz=float(values[j]),quadratic_projection_hz=float(p[j]),orthogonal_rest_hz=float(e[j]),q_applied_to_delta=False))
        for arm in ('c0','fitted_c'):
            h=arrays[case+'_'+arm+'_response'];weak=arrays[case+'_'+arm+'_weak']
            assert h.shape==(2,len(native))
            summed=np.zeros(2)
            for owner,role,ix,v,p,e in owners:
                all_v=h[:,ix]@v;low=h[:,ix]@p;high=h[:,ix]@e;summed+=all_v
                error=float(np.max(np.abs(all_v-low-high)))
                assert error<1e-10
                owner_rows.append(dict(case=case,arm=arm,owner=owner,role=role,points=len(ix),native_delta_RMS_hz=float(np.sqrt(np.mean(v*v))),
                    quadratic_delta_RMS_hz=float(np.sqrt(np.mean(p*p))),rest_delta_RMS_hz=float(np.sqrt(np.mean(e*e))),
                    total_east_m=float(all_v[0]*1000),total_north_m=float(all_v[1]*1000),
                    quadratic_east_m=float(low[0]*1000),quadratic_north_m=float(low[1]*1000),
                    rest_east_m=float(high[0]*1000),rest_north_m=float(high[1]*1000),
                    total_weak_axis_m=float(weak@all_v*1000),additivity_error_km=error))
            total=h@delta;low=h@smooth;high=h@rest
            assert np.allclose(total,summed,atol=1e-11,rtol=0)
            assert np.allclose(total,low+high,atol=1e-11,rtol=0)
            original=next(r for r in endpoints if r['case']==case and r['arm']==arm and r['method']=='original')
            corrected=next(r for r in endpoints if r['case']==case and r['arm']==arm and r['method']=='corrected')
            assert original['status']==corrected['status']=='complete'
            actual=np.array(corrected['endpoint_east_north_km'])-np.array(original['endpoint_east_north_km'])
            case_rows.append(dict(case=case,arm=arm,points=len(selected),predicted_east_m=float(total[0]*1000),predicted_north_m=float(total[1]*1000),
                quadratic_east_m=float(low[0]*1000),quadratic_north_m=float(low[1]*1000),rest_east_m=float(high[0]*1000),rest_north_m=float(high[1]*1000),
                actual_RF_endpoint_east_m=float(actual[0]*1000),actual_RF_endpoint_north_m=float(actual[1]*1000),
                predicted_norm_m=float(np.linalg.norm(total)*1000),actual_RF_endpoint_norm_m=float(np.linalg.norm(actual)*1000),
                linearization_difference_norm_m=float(np.linalg.norm(actual-total)*1000),
                corrected_original_gate_valid=corrected['original_single_arm_valid'],all_old_accepted_IDs_preserved=corrected['all_original_accepted_IDs_preserved'],
                owner_additivity_error_km=float(np.max(abs(total-summed))),component_additivity_error_km=float(np.max(abs(total-low-high)))))
    assert len(ordering)==159 and len({r['native_id']for r in ordering})==159
    table(HERE/'owner_response.csv',owner_rows);table(HERE/'case_response.csv',case_rows);table(HERE/'native_ordering.csv',ordering)
    labels=[r['case'][-4:]+' '+r['arm'].replace('fitted_c','fitted c')for r in case_rows]
    fig,axes=plt.subplots(2,1,figsize=(10,7),constrained_layout=True,sharex=True)
    x=np.arange(4)
    for ax,coord in zip(axes,('east','north')):
        for offset,key,label,color in [(-.27,f'quadratic_{coord}_m','Quadratic component','#009E73'),(-.09,f'rest_{coord}_m','Orthogonal remainder','#E69F00'),(.09,f'predicted_{coord}_m','Sum: frozen local response','#0072B2'),(.27,f'actual_RF_endpoint_{coord}_m','Actual RF endpoint change','#D55E00')]:
            ax.bar(x+offset,[r[key]for r in case_rows],width=.17,label=label,color=color)
        ax.axhline(0,color='.3',lw=.8);ax.grid(axis='y',alpha=.2)
        ax.set(ylabel=f'{coord.capitalize()} displacement (m)')
    axes[0].legend(ncol=2,fontsize=8)
    axes[1].set_xticks(x,labels)
    fig.suptitle('Posthoc explanation of measured CFO changes using saved local H\nNative deltas used once; fixed Gaussian/VI approximation, no GPS or accuracy forecast',fontsize=12)
    fig.savefig(HERE/'local_response.png',dpi=170);fig.savefig(HERE/'local_response.pdf');plt.close(fig)
    paths=[Path(__file__),OLD/'local_math.py',OLD/'response_arrays.npz',OLD/'complete_owner_ledger.json',
        ROOT/'measurement/corrections.json',ROOT/'measurement/RF_seal.json',ROOT/'position/execution.json',ROOT/'position/RF_seal.json']
    seconds=time.monotonic()-STARTED+1.
    if seconds>20:raise TimeoutError('20second saved-only budget exceeded')
    dump(HERE/'summary.json',dict(posthoc=True,tests=tests.testsRun,test_seconds=test_seconds,cumulative_numeric_seconds=seconds,
        initial_metadata_inspection_allowance_seconds=1.,actual_native_ids=159,no_additional_q=True,
        full_native_order_retained=True,position_RF_seal_sha256=sha(ROOT/'position/RF_seal.json'),
        case_rows=case_rows,owner_rows=owner_rows,not_an_accuracy_forecast=True,source_bindings={str(p):sha(p)for p in paths}))
    dump(HERE/'seal.json',dict(source_bindings={str(p):sha(p)for p in paths},
        files={str(p.relative_to(HERE)):sha(p)for p in HERE.iterdir()if p.is_file()and p.name!='seal.json'}))
    print(json.dumps(case_rows,indent=2))


if __name__=='__main__':main()
