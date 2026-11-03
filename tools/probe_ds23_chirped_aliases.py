"""Qualify carrier aliases/common-clock sensitivity after chirped RF fitting."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import copy
from pathlib import Path
import signal
import time
import numpy as np

from audit_ds23_targeted_differential_rf import reconstruct
from ds23_chirped_component_workspace import ChirpedComponentWorkspace
from ds23_common_probe_frequency import CommonProbeFrequency
from run_algo01_ds23_sample import ROOT,read,write,sha
from select_ds23_differential_information import OUT as PARENT

OUT=PARENT/'chirped_aliases'


class ConditionedRates:
    def __init__(self,p,rates):self.p=p;self.rates=np.asarray(rates,float)
    @property
    def segments(self):return self.p.segments
    @segments.setter
    def segments(self,value):self.p.segments=value
    def statistics(self,parameters,*args,**kwargs):
        result=self.p.statistics(np.r_[parameters,self.rates],*args,**kwargs)
        result['normal']=result['normal'][:6,:6];result['rhs']=result['rhs'][:6]
        return result


def one(record,source):
    case,probe=record['case'],record['probe'];path=OUT/f'{case}_probe{probe:06d}.json'
    if path.exists():return read(path)
    if not record.get('chirp_quality_checks_pass'):
        result=dict(case=case,probe=probe,status='not_eligible',RF_qualified=False,source_quality_checks=record.get('checks'))
        write(path,result);return result
    started=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s chirped carrier alias cap')));signal.alarm(180)
    try:
        p=ChirpedComponentWorkspace.from_workspace(reconstruct(source));folds=[]
        for parity in [0,1]:
            original=record['folds'][parity];alternatives=[]
            for offset in [-750.,750.]:
                v=copy.copy(p);v.start=p.start.copy();v.start[0]+=offset
                initial=np.asarray(original['fit']['parameters']).copy();initial[0]+=offset
                fitted=v.fit(initial,parity,iterations=100)
                held=v.statistics(fitted['parameters'],parity,derivatives=False,prediction=True)
                nominal=original['prediction']
                alternatives.append(dict(offset_hz=offset,fit=fitted,
                    held_gain_favoring_nominal=float(2*held['heldout_samples']*np.log(held['heldout_squared_error']/nominal['heldout_squared_error']))))
            folds.append(dict(alternative_carriers=alternatives))
        parameters=np.asarray(record['full']['parameters'])
        common=CommonProbeFrequency(ConditionedRates(p,parameters[6:]),parameters[:6]).optimize(iterations=40)
        change=abs(common['component_CFO_difference_hz']-record['full']['contrast'][0])
        checks=dict(source_chirp_quality=True,all_relative_carrier_aliases_resolved=all(a['held_gain_favoring_nominal']>10 for f in folds for a in f['alternative_carriers']),
            common_receiver_contrast_stable=change<=20.)
        result=dict(case=case,probe=probe,status='complete',job=record['job'],folds=folds,common_full=common,
            common_model_change_hz=change,RF_qualified=all(checks.values()),checks=checks,
            full=record['full'],declared_sigma_hz=max(record['conditional_CFO_sigma_hz'],change),
            carrier_epoch_relative_to_GLRT_s=record['carrier_epoch_relative_to_GLRT_s'],
            no_GPS_TLE_new_RF_or_position_fit=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,probe=probe,status='failed',error=repr(exc),RF_qualified=False)
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result)
    print(case,probe,result['status'],result.get('RF_qualified'),result.get('checks'),result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);source=read(PARENT/'RF_pilot.json');chirped=read(PARENT/'chirped_validation/evaluation.json');assert chirped['all_terminal']
    protocol=dict(source_sha256=sha(PARENT/'chirped_validation/evaluation.json'),
        selection='all chirp-quality-qualified probes, no geographic outcomes',relative_aliases_hz=[-750,750],
        common_three_part_frequency_conditioned_on_full_code_and_chirp_parameters=True,
        sigma_never_smaller_than_original_RF_or_chirp_bootstrap=True,workers=3,per_probe_seconds=180,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_chirped_component_workspace.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('chirped alias protocol changed')
    if not path.exists():write(path,protocol)
    lookup={(r['case'],r['probe']):r for r in source['rows']}
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,r,lookup[r['case'],r['probe']]) for r in chirped['rows']])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,RF_qualified=sum(r.get('RF_qualified',False) for r in rows)))


if __name__=='__main__':main()
