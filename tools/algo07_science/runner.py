"""ALGO07 frozen single-scan guarded reassociation orchestration.

Scientific branches copied from the qualified research runner. Only process,
storage and endpoint-reporting adapters differ; see the parity manifest.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import time
import numpy as np
from . import engine as e
from .validation import receiver_shared_check, clean
from .uniqueness import from_additional_checks
from .policy import select, POLICY
from .propagation import audit as audit_catalogue
from prototype_dsx01_continuous_position import latlon

SETTINGS=dict(policy=POLICY,process_limit_s=1200,
    methods=['combined_whole_family_replacement_only'],
    standalone_history=False,chaining=False,history='complete active and proposed causal history only after inherited and receiver-shared predictive admission',
    trigger='original top2 RF-influence families, >=0.5km summed influence, >=30 native points and >=2 tracks',
    nomination='original full72h causal bank coarse two-longest-track nomination; same finalists botharms',
    inherited_predictive='original five synchronized5s groups+5s guards; positive mean and >=4/5 wins botharms',
    added_predictive=dict(seed=20261111,folds=10,minimum_unique_folds=5,minimum_competitor_margin_exclusive=0.,
        models=['receiver_offset'],phase_sd_s=5.,noise_hz=150.,offset_sd_hz=300.,shared_rate_sd_hz_s=.5,
        phase_grid_s=[-30,30,.4],block_s=5,guard_s=5,held_group_fraction=.2),
    candidate_scope='all common nominees including incumbent; conditional on full-data nomination/graph/aliases/cavity calibration',
    destination_ownership='absent from both baseline-arm owner maps',
    phase_rounds=15,phase_tolerance_s=.01,phase_limit_s=30,position_iterations=40,
    starts=['published_fitted_c','family_omitted_fitted_c'],region_center=[37.906,-122.545],region_width_km=25,
    joint_acceptance='original gates/exact orbit/phase/solver/mixture phase interior/native owner checks, botharms; gains beyond existing shortlist penalty',
    controls='same two starts and budget under matched active history; bound by best qualified control, matched-prior published endpoint and original published objective',
    catalogue_eligibility='every381knots error0 and finite states; explicitly exclude only one uniform documented invalid SGP4 code in{1,2,3,4,6} at ALLknots; partial/mixed/unknown/nonfinite-error0 blocks',
    fallback='exact frozen published baseline on rejection, incomplete search, unexplained/partial/nonfinite propagation, worker failure or hardcap; no partial winner publication',
    truth='endpoint error metadata only, never nomination/guard/search/selection',
    production_modified=True)

def read(path):return json.loads(Path(path).read_text())

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+f'.tmp-{os.getpid()}')
    temporary.write_text(json.dumps(clean(value),indent=2,allow_nan=False)+'\n')
    os.replace(temporary,path)

def published_baseline(input_root,case):
    """Read exact published coordinates/objectives without launching RF search.

    RMS is unavailable from the compact published endpoint schema and remains
    null. This immutable summary is the supervisor's exact fallback authority.
    """
    z=read(input_root/'inputs'/(case+'.json'))
    published=read(input_root/'position'/case/'result.json')
    decision=published['decisions']['72h_30s']
    trial=published['trials'][decision['trial']] if decision['status']=='qualified' else None
    rows=trial['arms'] if trial else z['baseline_arms']
    baseline={}
    for arm in e.ARMS:
        row=rows[arm];point=row['endpoint_east_north_km']
        owners=dict(z['baseline_owners'][arm])
        if trial:
            for oid in trial['entry']['observation_ids']:
                if oid in owners:raise ValueError('Published ALGO06 native owner collision')
                owners[oid]=trial['entry']['norad']
        baseline[arm]=dict(x=point,error_m=e.previous.error(np.asarray(point)),objective=row['negative_twice_elbo'],
                           associated=len(owners),rms_hz=None)
    return baseline

def public_owners(terminal):
    if terminal['candidate'] is not None:
        return terminal['candidate']['published_owners']
    from leo.contracts.fast_graph_position_v5 import owners
    return owners(terminal['incumbent'])

def preflight_public(d,z,baseline,terminal):
    point=np.asarray(latlon(d['problems']['fitted_c'][1]))
    published=np.asarray([terminal['position']['latitude_deg'],terminal['position']['longitude_deg']])
    maximum=float(np.max(np.abs(point-published)))
    if maximum>1e-9:raise ValueError('RF replay does not match public ALGO06 fitted-c latitude/longitude')
    expected=public_owners(terminal)
    counts={}
    for arm in e.ARMS:
        if z['baseline_owners'][arm]!=expected[arm]:raise ValueError('Public ALGO06 native owner contract mismatch')
        if baseline[arm]['associated']!=len(expected[arm]):raise ValueError('Public ALGO06 native owner count mismatch')
        counts[arm]=len(expected[arm])
    return dict(public_fitted_c_maximum_difference_deg=maximum,tolerance_deg=1e-9,
                public_owner_counts=counts,public_owner_maps_equal=True)

def destination_owned(z,new):
    return any(int(new) in set(map(int,z['baseline_owners'][arm].values())) for arm in e.ARMS)

def score_record(hypothesis,pair,control,bounds):
    complete=all(pair.get(a) is not None and control.get(a) is not None for a in e.ARMS)
    gains={a:bounds[a]-pair[a]['objective']-hypothesis['penalty'] for a in e.ARMS} if complete else {}
    return dict(name=hypothesis['name'],hypothesis=hypothesis,pair=pair,control=control,gains=gains,
                accepted=bool(complete and all(v>0 for v in gains.values())),bounds=bounds)

def fallback(baseline,status,**metadata):
    return dict(policy=POLICY,selected=None,final=copy.deepcopy(baseline),review=[],baseline=copy.deepcopy(baseline),
                execution_status=status,production_modified=False,**metadata)

def fit_rows_complete(rows):
    expected={(a,s) for a in e.ARMS for s in ('published','family_omitted')}
    return (len(rows)==len(expected) and {(r.get('arm'),r.get('start')) for r in rows}==expected
            and all(r.get('status')=='complete' for r in rows))

def propagation_eligible(receipt,bank_failures):
    failures=receipt['failures']
    if not receipt['nominal_causality_verified'] or receipt['partial_or_unknown_blocks']:return False
    if any(r['classification']!='exclude_consistent_model_invalid_all_grid' for r in failures):return False
    excluded={int(r['norad']) for r in failures}
    return len(excluded)==len(failures) and excluded==set(map(int,bank_failures))

def run_worker(case,input_root,output_root):
    began=time.monotonic()
    if case != 'SCAN':raise ValueError('Private single-scan input required')
    from algo07_history import collect_private
    e.configure(input_root,output_root,collect_history=lambda request: collect_private(input_root/'history-bank.json',request))
    protocol=read(output_root/'protocol.json')
    out=output_root/case;out.mkdir(parents=True,exist_ok=True)
    baseline=copy.deepcopy(protocol['baselines'][case])
    d,z,replay=e.load_case(case)
    for arm,(p,x) in d['problems'].items():
        if not np.array_equal(x,np.asarray(baseline[arm]['x'])):raise ValueError('Published baseline coordinate replay mismatch')
        if abs(e.objective(p,d,x)-baseline[arm]['objective'])>1e-4:raise ValueError('Published baseline RF objective replay mismatch')
        if len(z['baseline_owners'][arm])!=baseline[arm]['associated']:raise ValueError('Published native ownership replay mismatch')
    write(out/'baseline.json',baseline);write(out/'replay.json',replay)
    public=preflight_public(d,z,baseline,read(input_root/'exports'/case/'published-algo06.json'))
    write(out/'public_replay.json',public)
    ledger=e.rec.causal_records(case,z)
    write(output_root/'ledgers'/case/'tle-ledger.json',dict(causal=ledger))
    ranking,targets=e.rank_families(d,z)
    write(out/'trigger.json',dict(ranking=ranking,selected=targets))
    records=[];guards={};failures=[];history=None;hd=None
    nums=[];bank=None;propagation_failures=[];propagation=None
    if targets:
        nums,bank,propagation_failures=e.rec.bank_for(ledger,z['scan_receipt']['origin_utc_ns'])
        propagation=audit_catalogue(case,input_root/'catalogues'/(case+'.json'),input_root/'inputs'/(case+'.json'),'elements')
        write(out/'catalogue_eligibility.json',propagation)
    eligible=(not targets or (propagation_eligible(propagation,propagation_failures)
              and len(nums)+len(propagation_failures)==len(ledger)
              and np.isfinite(bank['position_km']).all() and np.isfinite(bank['velocity_km_s']).all()))
    if not eligible:
        result=fallback(baseline,'propagation_fallback',case=case,targets=targets,
                        propagation_failures=propagation_failures,records=[],guards={},history=None,
                        seconds=time.monotonic()-began,protocol_sha256=sha(output_root/'protocol.json'))
        write(out/'worker_result.json',result)
        return result
    for old in targets:
        folder=out/str(old);folder.mkdir(exist_ok=True)
        screen=e.rec.screen(d,z,old,nums,bank,folder)
        write(folder/'screen.json',screen)
        proposals=[h for h in screen.get('proposals',[]) if 'prediction_limit' not in h
                   and set(map(int,h['mapping'].values()))=={int(h['norad'])}
                   and int(h['norad'])!=int(old)
                   and all(h['predictive'][a]['pass_check'] for a in e.ARMS)]
        admitted=[];shared=None
        for h in proposals:
            if destination_owned(z,h['norad']):
                guards[h['name']]=dict(passed=False,status='rejected',model='receiver_offset',reason='destination_already_owned')
                continue
            if shared is None:
                shared=receiver_shared_check(d,z,screen,old,h['norad'],ledger)
                write(folder/'receiver_shared_check.json',shared)
            guard=from_additional_checks(dict(shared,new=h['norad']))
            guards[h['name']]=guard
            write(folder/(h['name']+'-guard.json'),guard)
            if guard['passed']:admitted.append(h)
        if not admitted:continue
        # No history read/completion or joint refit occurs before RF admission.
        if hd is None:
            hd,history=e.complete_history(d,z,case,e.active_ids(d),out/'incumbent_history')
            write(out/'history.json',history)
        starts={'published':d['problems']['fitted_c'][1],
                'family_omitted':np.asarray(screen['cavity']['fitted_c']['x'])}
        control_rows=e.fit_rows(hd,z,starts,set(),folder/'control_history.json')
        if not fit_rows_complete(control_rows):
            result=fallback(baseline,'incomplete_fit_fallback',case=case,stage='matched_control',target=old,
                            records=records,guards=guards,failures=control_rows,seconds=time.monotonic()-began)
            write(out/'worker_result.json',result);return result
        controls=e.paired(control_rows)
        matched_published={a:e.objective(hd['problems'][a][0],hd,d['problems'][a][1]) for a in e.ARMS} if all(controls.values()) else {}
        bounds={a:min(controls[a]['objective'],baseline[a]['objective'],matched_published[a]) for a in e.ARMS} if all(controls.values()) else {}
        for h in admitted:
            trial=folder/(h['name']+'-combined');trial.mkdir(exist_ok=True)
            candidate,hinfo=e.complete_history(hd,z,case,set(h['mapping'].values()),trial/'history')
            candidate=e.remap(candidate,z,case,h)
            fits=e.fit_rows(candidate,z,starts,set(h['allowed_families']),trial/'fits.json')
            if not fit_rows_complete(fits):
                result=fallback(baseline,'incomplete_fit_fallback',case=case,stage='admitted_candidate',target=old,
                                records=records,guards=guards,failures=fits,seconds=time.monotonic()-began)
                write(out/'worker_result.json',result);return result
            pair=e.paired(fits)
            record=score_record(h,pair,controls,bounds)
            record.update(target=old,history=hinfo,fits_path=str(trial/'fits.json'),matched_published_objectives=matched_published)
            records.append(record);write(trial/'decision.json',record)
            print(case,h['name'],record['accepted'],flush=True)
    choice=select(baseline,records,guards)
    result=dict(choice,case=case,baseline=baseline,records=records,guards=guards,targets=targets,history=history,
                failures=failures,propagation_failures=propagation_failures,catalogue_eligibility=propagation,seconds=time.monotonic()-began,
                execution_status='complete',protocol_sha256=sha(output_root/'protocol.json'),production_modified=False)
    write(out/'worker_result.json',result)
    return result
