"""Disjoint raw-symbol validation of within-probe frequency variation.

Both constant and three-part CFOs are learned from training symbols only.
Timing/code rate remain conditioned on an earlier whole-probe fit. This tests
RF prediction, not whether late frequency is a settled orbital observable.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json
import signal
import numpy as np
from ds23_joint_component_refinement import JointComponentWorkspace
from ds23_probe_frequency_profile import frequency_only_fit
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_frequency_profile_validation'
BULK=Path('/srv/bulk/leo/research/ds23-frequency-profile-validation-20261021')
SOURCE=ROOT/'reports/2026_10_21_ds23_joint_component_refinement'


class SymbolFold:
    def __init__(self,p,parity):self.p,self.parity=p,parity
    @property
    def segments(self):return self.p.segments
    def statistics(self,parameters,**kwargs):return self.p.statistics(parameters,self.parity,**kwargs)


def one(item,old):
    job=item['job'];target=BULK/(job['group']+f"_probe{job['probe']:06d}.json")
    if target.exists():return read(target)
    def timeout(*_):raise TimeoutError('90-second within-probe RF prediction cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(90);record=dict(case=job['case'],group=job['group'],probe=job['probe'])
    try:
        with np.load(Path(item['source'])/'panels'/(job['case']+'.npz'),allow_pickle=False) as z:
            metadata=json.loads(str(z['metadata_json']));point=next(p for p in metadata['points'] if p['probe']==job['probe'])
            v=z[point['window_key']][:,point['receiver_offset']]
        y=v[:,0].astype(float)+1j*v[:,1].astype(float)
        p=JointComponentWorkspace(y,metadata['sample_rate_hz'],job['edge'],[job['first']['epoch'],job['second']['epoch']],
            [item['fit']['first_fit'],item['fit']['second_fit']]);initial=np.array(old['full']['parameters'])
        all_segments=p.segments;thirds=np.array_split(np.arange(len(all_segments)),3);folds=[]
        for parity in [0,1]:
            p.segments=all_segments;fold=SymbolFold(p,parity)
            baseline=frequency_only_fit(fold,initial)
            base_prediction=p.statistics(baseline['parameters'],parity,derivatives=False,prediction=True)
            parts=[];squared_error,count,raw=0.,0,0.
            for indices in thirds:
                p.segments=[all_segments[i] for i in indices];fit=frequency_only_fit(fold,initial)
                prediction=p.statistics(fit['parameters'],parity,derivatives=False,prediction=True)
                squared_error+=prediction['heldout_squared_error'];count+=prediction['heldout_samples'];raw+=prediction['heldout_raw_energy']
                parts.append(dict(fit=fit,prediction=prediction))
            if count!=base_prediction['heldout_samples'] or abs(raw-base_prediction['heldout_raw_energy'])>1e-5*raw:
                raise ValueError('held-out sample support changed')
            gain=float(2*count*np.log(base_prediction['heldout_squared_error']/squared_error))
            folds.append(dict(parity=parity,baseline=baseline,baseline_prediction=base_prediction,parts=parts,
                piecewise_heldout_squared_error=squared_error,heldout_profile_gain=gain,
                heldout_SSE_fractional_improvement=1-squared_error/base_prediction['heldout_squared_error']))
        checks=dict(both_symbol_folds_predict_better=all(f['heldout_profile_gain']>10 for f in folds),
            all_frequency_estimates_interior=not any(v['search_boundary'] for f in folds for v in [f['baseline']]+[p['fit'] for p in f['parts']]),
            both_folds_CFO_profiles_consistent=bool(max(np.max(abs(np.array(folds[0]['parts'][k]['fit']['CFO_hz'])-
                np.array(folds[1]['parts'][k]['fit']['CFO_hz']))) for k in range(3))<=30))
        record.update(status='complete',folds=folds,checks=checks,RF_profile_qualified=all(checks.values()),
            original_whole_probe_timing_rate_conditioned=True,frequency_and_channel_updates_training_symbols_only=True,
            receiver_settling_and_absolute_Doppler_interpretation_not_established=True,no_CFO_or_position_correction_applied=True)
    except Exception as exc:record.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    write(target,record);return record


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);source=read(SOURCE/'protocol.json');evaluation=read(SOURCE/'evaluation.json')
    pilot=ROOT/'reports/2026_10_21_ds23_frequency_profile/evaluation.json'
    for name,digest in source['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=digest:raise ValueError('native two-component fitter changed')
    lookup={(r['case'],r['probe']):r for r in evaluation['rows']}
    protocol=dict(jobs=source['jobs'],workers=8,per_probe_seconds=90,pilot_sha256=sha(pilot),
        validate_all46_probes_not_only_promising_profiles=True,folds='OFDM symbol parity',
        both_constant_and_piecewise_CFOs_fitted_on_training_symbols_only=True,
        common_whole_probe_timing_code_rate_conditioned_and_channel_dimension_unchanged=True,
        no_GPS_TLE_satellite_selection_or_new_RF=True,no_position_correction=True,
        source_protocol_sha256=sha(SOURCE/'protocol.json'),source_evaluation_sha256=sha(SOURCE/'evaluation.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_probe_frequency_profile.py',ROOT/'tools/ds23_joint_component_refinement.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('RF-profile validation protocol changed')
    if not target.exists():write(target,protocol)
    rows=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(one,item,lookup[item['job']['case'],item['job']['probe']]) for item in protocol['jobs']]):
            r=future.result();rows.append(r);print(r['group'],r['probe'],r['status'],r.get('checks'),r.get('error'),flush=True)
    complete=[r for r in rows if r['status']=='complete']
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,complete=len(complete),
        both_folds_predict_better=sum(r['checks']['both_symbol_folds_predict_better'] for r in complete),
        RF_qualified=sum(r['RF_profile_qualified'] for r in complete),
        median_heldout_profile_gain=float(np.median([f['heldout_profile_gain'] for r in complete for f in r['folds']])),
        no_CFO_or_position_adoption=True,not_independent_scan_or_location_generalization=True,
        source_protocol_sha256=sha(target)))


if __name__=='__main__':main()
