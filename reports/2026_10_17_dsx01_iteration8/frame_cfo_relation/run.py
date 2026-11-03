"""Bounded all693 descriptive audit; no old script execution or orbit model."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
import numpy as np
from relation import branches,phase_prediction,compare_cfo

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parents[1]
INVENTORY=REPORTS/'2026_10_17_dsx01_iteration6/frame_phase_inventory'
DATA=REPORTS/'2026_10_16_dsx01_fast_association_losses'
TRACKS=REPORTS/'2026_10_16_dsx01_models/model_b.py'


def digest(p):return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()
def plain(v):
    if isinstance(v,dict):return {k:plain(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [plain(x) for x in v]
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    return v
def save(p,value):
    with Path(p).open('x') as stream:json.dump(plain(value),stream,indent=2,allow_nan=False);stream.write('\n')


def run():
    begun=time.monotonic();deadline=begun+120
    paths=[HERE/'relation.py',HERE/'test_relation.py',HERE/'run.py',INVENTORY/'manifest.json',INVENTORY/'observations.jsonl',DATA/'context-observations.jsonl',TRACKS]
    save(HERE/'protocol-v2.json',dict(supersedes='protocol.json: preflight stopped on manifest dictionary schema before CFO load; no scientific results produced',maximum_seconds=120,cohort='All693 frozen original winners; selected15windows descriptive only, not runtime inference inputs',
        selection='ExactoldB automatic450Hz/45s/24point partition separately persource; nowindowIDs supplied tobuilder',
        branch_guard='Splitnonpositivefirstframetime,adjacentgap>5s,orprincipalphasestep>quarterphysicalperiod; alternatingTRAINanchors alsoquarterperiodguard. Numerical continuity only, physicalcyclecountunproved.',
        phase_fit='Even-index firstframephaseanchors only;degree2 if>=5TRAINanchors elselinear if>=3; totalN>=5. Derivative evaluated at CFOsupportcenter. NoCFO inphasefit.',
        cfo_center='y=CFO/actualRF andx=phase_derivative/Fs; subtract eachsegmentTRAINmean independently; scoreoddpoints',
        physical_controls='Fixed yprediction=+x and−x; equivalentCFOHz factor±RF/Fs, no scale learned for physical interpretation',
        descriptive='Report TRAIN-only beta and heldresiduals; quadraticphase derivative islinearintime, so arbitrary persegmentbeta cannotaddinformation beyond CFOlineartrend. No clock/identity/recoveryclaim.',
        null='32fixedseedwithinsegmentodd-CFOpermutations; labels andphasefits frozen. Bothphysicalsigns andpooledTRAINbeta reported, not selected.',
        limitations='WindowandCFOselectedcohort/tracklets; carrierCFO andphase fromsamewinningacquisition. This isnot independent-validation/knowntransmittedepoch evidence.',
        source_sha256={str(p):digest(p) for p in paths}))
    import test_relation
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_relation))
    if not tests.wasSuccessful():raise AssertionError('Component tests failed')
    manifest=json.loads((INVENTORY/'manifest.json').read_text())['files']
    for name,sha in manifest.items():assert digest(INVENTORY/name)==sha
    records=[json.loads(s) for s in (INVENTORY/'observations.jsonl').read_text().splitlines()];assert len(records)==693
    frozen={(r['source_id'],r['observation_id']):r for s in (DATA/'context-observations.jsonl').read_text().splitlines() if (r:=json.loads(s))}
    spec=importlib.util.spec_from_file_location('frame_cfo_original_tracklets',TRACKS);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    groups=[];usable=[];point_records=[];source_tracklets={}
    for sid in sorted({r['source_id'] for r in records}):
        source=sorted([r for r in records if r['source_id']==sid],key=lambda r:(r['cfo_support_center_session_relative_s'],r['observation_id']))
        y=[]
        for r in source:
            f=frozen[sid,r['observation_id']]
            assert f['time_s']==r['cfo_support_center_session_relative_s'] and f['actual_rf_hz']==r['actual_rf_hz']
            assert f['receiver']-1==r['receiver_contract'] and f['channel']==r['channel']
            y.append(f['measured_cfo_hz'])
        obs=SimpleNamespace(times_s=np.array([r['cfo_support_center_session_relative_s'] for r in source]),measured_hz=np.array(y),
            rf_hz=np.array([r['actual_rf_hz'] for r in source]),receiver=np.array([r['receiver_contract'] for r in source]),channel=np.array([r['channel'] for r in source]))
        labels=module.build_tracklets(obs,gate_hz=450.,maximum_duration_s=45.,maximum_points=24)
        source_tracklets[sid]=len(np.unique(labels))
        for label in np.unique(labels):
            original=np.flatnonzero(labels==label)
            original=original[np.argsort([source[i]['winner']['first_frame_session_relative_s'] for i in original],kind='stable')]
            first=np.array([source[i]['winner']['first_frame_session_relative_s'] for i in original])
            phase=np.array([source[i]['winner']['positive_arrival_phase_samples'] for i in original]);fs=source[original[0]]['sample_rate_hz']
            for branch,part in enumerate(branches(first,phase,fs)):
                indexes=original[part];r=source[indexes[0]];first_part=first[part];phase_part=phase[part]
                row=dict(source_id=sid,receiver=int(r['receiver_contract']),channel=int(r['channel']),tracklet=int(label),branch=branch,
                    observations=len(part),start_first_frame_s=float(first_part[0]),span_s=float(np.ptp(first_part)),
                    eligible=False,reason='fewer_than5rows',degree=None,beta=None,phase_train_rms_samples=None,phase_held_rms_samples=None,
                    max_support_offset_s=max(source[i]['cfo_support_center_session_relative_s']-source[i]['winner']['first_frame_session_relative_s'] for i in indexes),
                    regions=sorted({source[i]['region_id'] for i in indexes}))
                if len(part)>=5:
                    support=obs.times_s[indexes]
                    try:
                        if len(np.unique(obs.rf_hz[indexes]))!=1:raise ValueError('multiple_actual_RF_in_segment')
                        p=phase_prediction(first_part,phase_part,support,fs)
                        c=compare_cfo(obs.measured_hz[indexes],obs.rf_hz[indexes],support,p)
                        row.update(eligible=True,reason='qualified_numerical_branch_not_verifiedcycle',degree=p['degree'],beta=c['beta'],
                            phase_train_rms_samples=p['phase_train_rms_samples'],phase_held_rms_samples=p['phase_held_rms_samples'],
                            curvature_samples_s2=float(2*p['coefficients'][2]) if p['degree']==2 else 0.)
                        rms=lambda a:float(np.sqrt(np.mean(a*a)))*1e6
                        for name,pred in [('baseline',np.zeros(len(part))),('plus',c['x_centered']),('minus',-c['x_centered']),('beta',c['descriptive_prediction']),('time_only',c['time_only_prediction'])]:
                            row['held_'+name+'_rms_ppm']=rms((c['y_centered']-pred)[c['held']])
                        row['held_points']=int(c['held'].sum());row['train_points']=int(c['train'].sum())
                        usable.append(dict(group=len(groups),row=row,**c))
                        for j,index in enumerate(indexes):
                            point_records.append(dict(source_id=sid,observation_id=source[index]['observation_id'],group=len(groups),
                                receiver=row['receiver'],channel=row['channel'],first_frame_s=first_part[j],support_center_s=support[j],
                                held=bool(c['held'][j]),x_centered=c['x_centered'][j],y_centered=c['y_centered'][j],
                                time_only_prediction=c['time_only_prediction'][j],descriptive_prediction=c['descriptive_prediction'][j]))
                    except ValueError as error:row['reason']=str(error)
                groups.append(row)
        if time.monotonic()>=deadline:raise TimeoutError('120s audit allowance')
    def aggregate(items):
        if not items:return None
        xx=sum(float(c['x_centered'][c['train']]@c['x_centered'][c['train']]) for c in items)
        xy=sum(float(c['x_centered'][c['train']]@c['y_centered'][c['train']]) for c in items)
        beta=xy/xx if xx>1e-24 else None
        y=np.concatenate([c['y_centered'][c['held']] for c in items]);x=np.concatenate([c['x_centered'][c['held']] for c in items])
        predictions={'baseline':np.zeros(len(y)),'plus':x,'minus':-x,'pooled_beta':np.zeros(len(y)) if beta is None else beta*x,
            'segment_beta':np.concatenate([c['descriptive_prediction'][c['held']] for c in items]),
            'time_only':np.concatenate([c['time_only_prediction'][c['held']] for c in items])}
        rms={key:float(np.sqrt(np.mean((y-pred)**2)))*1e6 for key,pred in predictions.items()}
        rng=np.random.default_rng(5301);null={key:[] for key in ['plus','minus','pooled_beta']}
        for _ in range(32):
            shuffled=np.concatenate([rng.permutation(c['y_centered'][c['held']]) for c in items])
            for key in null:null[key].append(float(np.sqrt(np.mean((shuffled-predictions[key])**2)))*1e6)
        return dict(groups=len(items),observations=sum(len(c['held']) for c in items),train_points=sum(int(c['train'].sum()) for c in items),
            held_points=len(y),pooled_train_beta=beta,held_rms_ppm=rms,
            max_segment_beta_time_only_discrepancy_ppm=float(np.max(abs(predictions['segment_beta']-predictions['time_only']),initial=0))*1e6,
            null_held_rms_ppm=null,null_lower_tail={key:(1+sum(value<=rms[key] for value in values))/33 for key,values in null.items()})
    strata=[]
    for sid in sorted(source_tracklets):
        for rx,ch in sorted({(g['receiver'],g['channel']) for g in groups if g['source_id']==sid}):
            candidates=[c for c in usable if c['row']['source_id']==sid and c['row']['receiver']==rx and c['row']['channel']==ch]
            strata.append(dict(source_id=sid,receiver=rx,channel=ch,summary=aggregate(candidates)))
    summary=dict(original_observations=693,source_tracklets=source_tracklets,phase_subsegments=len(groups),eligible_groups=len(usable),
        eligible_observations=sum(g['observations'] for g in groups if g['eligible']),excluded_observations=sum(g['observations'] for g in groups if not g['eligible']),
        informative_quadratic_groups=sum(c['row']['degree']==2 for c in usable),all_eligible=aggregate(usable),
        quadratic_only=aggregate([c for c in usable if c['row']['degree']==2]),strata=strata,groups=groups,
        component_tests=tests.testsRun,orbit_or_localization_fit_calls=0,source_records=693,
        elapsed_seconds=time.monotonic()-begun,protocol_sha256=digest(HERE/'protocol-v2.json'),
        conclusion='Descriptive fixed-sign comparison and held residuals only. No physical clock/identity/recovery conclusion; arbitrary quadratic-derivative beta duplicates a time trend.')
    save(HERE/'results.json',summary)
    keys=sorted(set().union(*(g.keys() for g in groups)))
    with (HERE/'groups.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(plain(groups))
    save(HERE/'points.json',point_records)
    print(json.dumps(plain({key:summary[key] for key in ['phase_subsegments','eligible_groups','eligible_observations','excluded_observations','informative_quadratic_groups','all_eligible','elapsed_seconds']})),flush=True)


if __name__=='__main__':run()
