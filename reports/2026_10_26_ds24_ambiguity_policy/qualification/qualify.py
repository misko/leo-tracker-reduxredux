"""Frozen complete-owner nomination and necessary adequacy diagnostics."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

START=time.monotonic()
import numpy as np
from scipy.linalg import solve_triangular
import adequacy

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
PRIOR=Path('/srv/bulk/leo/research/ds24-ambiguity-position-r01/inventory')
WITNESS=Path('/srv/bulk/leo/research/ds24-rx2-witness-r01/scientific')
sys.path.insert(0,str(WITNESS))
import witness02 as w
sr=w.sr;k=w.k;r=w.r
ARMS=('c0','fitted_c');CAP=600.
COUNTS=[87,29,40,51]

def write(name,x):r.write_new(HERE/name,x)
def npz(name,**arrays):
    p=HERE/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:np.savez_compressed(f,**arrays)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def threads():
    if any(os.environ.get(z)!='1' for z in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):raise ValueError('BLAS1 required')

def witness_choice(rows,target):
    # Explicit metadata whitelist: no nominated candidate/alias/RMS enters.
    pool=[]
    for q in rows:
        if q['case']!=target['case'] or q['component']==target['component']:continue
        m={z:q[z] for z in ('component','receiver','channel','rf_hz','points','start_s','end_s','span_s','observation_ids','eligible','exclusion_reasons')}
        m['time_overlap_s']=max(0.,min(q['end_s'],target['end_s'])-max(q['start_s'],target['start_s']))
        m['different_receiver']=q['receiver']!=target['receiver'];m['identical_RF']=q['rf_hz']==target['rf_hz']
        pool.append(m)
    good=sorted([q for q in pool if q['eligible']],key=lambda q:(not q['different_receiver'],not q['identical_RF'],-q['time_overlap_s'],-q['points'],q['component']))
    return dict(all_other_owner_metadata=pool,selected=good[0] if good else None,
        selection_independent_of_candidate_columns=True,same_family_validated=False,scored_in_this_branch=False)

def compact(row):
    omit={'residual_hz','innovations_hz','times_s','observation_ids','conditional_residual_hz','profile_residual_hz'}
    return {key:val for key,val in row.items() if key not in omit}

def trace(row):
    case=row['case'];component=row['component'];base=r.SOURCE/case
    fit=r.read(base/'fit_radio_noise.json');selected=next(q for q in fit['choices'] if q['hypothesis']==fit['selected_hypothesis'])
    canonical=r.read(r.SOURCE/'family_cavity/position'/f'{case}.json')
    node=canonical['selected']['node'] if canonical['accepted'] else canonical['baseline_node']
    index=next(i for i,q in enumerate(node['seed']['rows']) if q['component']==component)
    archived=node['seed']['rows'][index]
    original=next(q for q in selected['node']['seed']['rows'] if q['component']==component)
    result=r.read(base/'result.json');algo=r.read(base/'algo02_result.json')
    selected_metrics={a:[compact(q) for q in selected['arms'][a]['metrics']['tracks'] if q['component']==component] for a in ARMS}
    final_metrics={a:[compact(q) for q in result['arms'][a]['metrics']['tracks'] if q['component']==component] for a in ARMS}
    trim=next((q for q in result['trims'] if q['component']==component),None)
    histories={z:[q for q in result[z] if component in q.get('rejected_components',[])] for z in ('exclusion_history','post_salvage_history')}
    histories['ALGO02_curved_gate_history']=[q for q in algo['curved_gate_history'] if component in q['failed']]
    obs={q['observation_id']:q for q in r.read(base/'observations.json')};track=next(q for q in r.read(base/'tracks.json') if q['key']==component)
    gauge=np.asarray([obs[oid]['measured_cfo_hz'] for oid in track['observation_ids']])-np.asarray(track['values'])
    integer=np.rint(gauge/k.PERIOD).astype(int)
    return dict(case=case,component=component,canonical=compact(archived),original_selected_hypothesis=fit['selected_hypothesis'],
        original_selected_row=compact(original),canonical_label_matches_original=archived['candidate_index']==original['candidate_index'],
        original_selected_phase_rounds={a:selected['arms'][a]['phase_rounds'] for a in ARMS},
        original_fixed_fit_metrics=selected_metrics,final_initial_algorithm_metrics=final_metrics,
        initial_failed=component in result['initial_failed_components'],histories=histories,
        stored_salvage=trim,complete_source_not_trimmed_here=True,
        original_gate_epoch_scalar_details_unavailable=any(histories.values()),
        graph_to_native_alias_integers=sorted(set(integer.tolist())),graph_native_gauge_max_error_Hz=float(np.max(abs(gauge-integer*k.PERIOD))),
        native_ids=track['observation_ids'],old_raw_gate_source_metrics_must_keep_original_label=True)

def entry_for(d,row):
    i=next(i for i,t in enumerate(d['scan'].tracks) if t['key']==row['component'])
    t=d['scan'].tracks[i]
    if t['observation_ids']!=row['observation_ids']:raise ValueError('complete native owner changed')
    cov=r.read(PRIOR/'ownership'/row['case']/'parent.json')['coverage']
    if any(set(row['observation_ids'])&set(cov[a]['accepted_observation_ids']) for a in ARMS):raise ValueError('parent accepted-ID overlap')
    return w.clean_entries(d,[dict(component=t['key'],track_index=i,observation_ids=t['observation_ids'],points=len(t['times']))])[0]

def component(d,x,entry):
    comp=w.background(d,d['_arm'],x,[entry]);cov=comp['covariance'];root=np.linalg.cholesky(cov)
    meta=d['scan'].fixed_window_noise
    sigma=np.array([meta['per_observation_noise_sigma_hz'][o] if meta['extra_parameter_BIC_gain']>0 else d['scan'].radio_sigma_hz for o in entry['observation_ids']])
    minimum=float(np.min(sigma)*np.sqrt(2))
    if np.linalg.eigvalsh(cov).min()<minimum**2*(1-1e-8):raise ValueError('noise covariance lower bound failed')
    aliases,shifts=k.alias_vectors(np.zeros(len(comp['raw']),int),np.arange(-4,5));observer=sr.geodetic_to_ecef_km(*k.latlon(x),0.)
    comp.update(d=w.owner_context(d,entry),root=root,observer=observer,base_logdet=float(2*np.log(np.diag(root)).sum()),noise_minimum_sd=minimum,
        aliases=aliases,shifts=shifts,whitened_aliases=solve_triangular(root,shifts.T,lower=True).T)
    return comp

def prepare():
    threads();began=START;sr.alarm(120.)
    prior=r.read(PRIOR/'results.json');inventory=r.read(PRIOR/'inventory.json');targets=[];contexts=[]
    for chosen in prior['selection']:
        row=next(q for q in inventory['sources'] if q['case']==chosen['case'] and q['component']==chosen['component']);targets.append(row)
    if [q['case'] for q in targets]!=[f'DS24-{i:04d}' for i in range(14,18)] or [q['points'] for q in targets]!=COUNTS:raise ValueError('original four panel changed')
    write('metadata.json',dict(targets=targets,witness_availability={q['case']:witness_choice(inventory['sources'],q) for q in targets},no_new_RF_comparison=True))
    for row in targets:
        case=row['case'];write(Path(case)/'original_trace.json',trace(row))
        d=r.context(case);x=np.asarray(d['arms']['c0']['endpoint_east_north_km']);d=w.at_common_position(d,x);entry=entry_for(d,row);checks={}
        for a in ARMS:
            cd,info=k.cavity(d,[],a);cd['_arm']=a
            if not w.hard_parent(info):raise ValueError('original fixed-parent hard check failed')
            comp=component(cd,x,entry)
            # Actual reload/redaction path: copying only target CFO must shift
            # raw by exactly that change, never covariance/old calibration.
            dd=copy.copy(cd);scan=copy.copy(cd['scan']);scan.tracks=list(scan.tracks);t=dict(scan.tracks[entry['track_index']]);scan.tracks[entry['track_index']]=t
            t['values']=np.asarray(t['values'])+1000.;scan.tracks[entry['track_index']]=t;dd['scan']=scan
            red=component(dd,x,entry)
            errors=dict(covariance=float(np.max(abs(red['covariance']-comp['covariance']))),parent_coefficients=float(np.max(abs(red['parent_coefficients']-comp['parent_coefficients']))),parent_noise=float(np.max(abs(red['parent_noise']-comp['parent_noise']))),raw=float(np.max(abs(red['raw']-comp['raw']-1000.))))
            if max(errors.values())>1e-8:raise ValueError('actual target redaction failed')
            npz(Path(case)/(a+'_original.npz'),raw=comp['raw'],covariance=comp['covariance'],q=comp['q'],values=d['scan'].tracks[entry['track_index']]['values'],times=d['scan'].tracks[entry['track_index']]['times'],native_ids=np.asarray(entry['observation_ids']),x=x)
            write(Path(case)/(a+'_original.json'),info);checks[a]=dict(redaction=errors,hard_parent=True,original_remaining_gates_pass=info['original_remaining_gates_pass'])
        write(Path(case)/'entry.json',entry);contexts.append(dict(case=case,x=x,checks=checks))
    signal.setitimer(signal.ITIMER_REAL,0);write('preparation.json',dict(seconds=time.monotonic()-began,actual_contexts=contexts,no_new_scores=True))
    freeze_start=time.monotonic()
    bindings={str(p):sha(p) for p in [PRIOR/'results.json',PRIOR/'inventory.json',PRIOR/'protocol.json',PRIOR/'lean_publication.json',HERE/'metadata.json',HERE/'PROTOCOL.md',HERE/'adequacy.py',HERE/'qualify.py',HERE/'test_qualification.py',HERE/'test_receipt.json',HERE/'preparation.json',ROOT/'COORDINATOR_PLAN.md']}
    for q in targets:
        case=q['case']
        for p in [PRIOR/'ownership'/case/'parent.json',r.SOURCE/'family_cavity/position'/f'{case}.json']+[r.SOURCE/case/n for n in ('tracks.json','observations.json','bank.npz','radio_noise.json','receipt.json','nominal_elements.json','fit_radio_noise.json','result.json','algo02_result.json')]+[r.SOURCE/'causal_phase_history'/f'{case}.json',r.SOURCE/'causal_phase_history'/f'{case}_forecast.json']:
            bindings[str(p)]=sha(p)
        for name in ('previous.tle','receipt.json','previous_receipt.json'):
            p=r.SOURCE/'causal_prior'/case/name;bindings[str(p)]=sha(p)
    for m in list(sys.modules.values()):
        p=getattr(m,'__file__',None)
        if p and p.endswith('.py') and (p.startswith(str(r.REPO)) or p.startswith('/srv/bulk/leo/research/')):bindings[p]=sha(p)
    protocol=dict(schema='frozen-four-owner-prerequisites/v1',source_input_hashes=bindings,targets=[{z:q[z] for z in ('case','component','points','candidate_norad','observation_ids','row_index','track_index')} for q in targets],
        preparation_seconds=r.read(HERE/'preparation.json')['seconds'],test_seconds=r.read(HERE/'test_receipt.json')['seconds'],freeze_seconds=time.monotonic()-freeze_start,cap_worker_seconds=600,workers=2,BLAS_threads=1,maximum_owner_arm_slots=8,maximum_physical_candidate_slots=64,
        exact_pool='ordinary c0top8 sharedbotharms; no forcedoldlabel',cavity='per-owner union8 removedcurved+predictive;5fixedphase refreshes',
        adequate_source_is_not_identity_probability=True,qualified_new_identity_requires_original_support_and_shared_hierarchy=True,
        metadata_witness_not_counted_as_support=True,no_position_fits=True,no_GPS_or_new_RF=True)
    write('protocol.json',protocol);print('PREPARED',sha(HERE/'protocol.json'),flush=True)

def verify():
    p=r.read(HERE/'protocol.json');receipt=r.read(ROOT/'audit/qualification_preflight.json')
    if not receipt['all_passed'] or receipt['protocol_sha256']!=sha(HERE/'protocol.json'):raise ValueError('matching independent preflight required')
    for file,h in p['source_input_hashes'].items():
        if sha(file)!=h:raise ValueError('frozen source/input changed: '+file)
    return p

def diagnose(d,candidate,comp,entry,target,best):
    diagnostic=adequacy.phase_map(candidate,comp,sr,np.nan)
    times=np.asarray(comp['d']['target_track']['times'])
    for label,key in [('conservative_gate','conservative_raw_hz'),('fullmode_gate','fullmode_raw_hz')]:
        diagnostic[label]=adequacy.source_gate(diagnostic[key],times,d['scan'].white[entry['track_index']],diagnostic['nominal_elevation_deg'])
    from run_ds23_combined_recovery_full import growth_supported
    diagnostic.update(norad=best['norad'],original_growth_supported=bool(growth_supported(d['base'],dict(candidate_index=best['candidate_index'],rows=[target['row_index']]))),
        requires_shared_family_restoration=best['candidate_index'] in d['original_protected'],
        independent_owner_prediction_validated=False,original_supported_slot=best['candidate_index'] in d['base'].supported,
        conservative_gate_is_necessary_only=True)
    return diagnostic

def score_owner(target,arm,deadline):
    case=target['case'];sr.alarm(deadline-time.monotonic());d=r.context(case);x=np.asarray(d['arms']['c0']['endpoint_east_north_km']);d=w.at_common_position(d,x)
    entry=r.read(HERE/case/'entry.json');screen=r.read(HERE/case/'c0_screen.json');pool=screen['candidate_indices'];norads=screen['candidate_norads']
    cd,info=k.cavity(d,pool,arm);write(Path(case)/(arm+'_cavity.json'),info)
    if not w.hard_parent(info):raise ValueError('cavity hard parent check failed')
    cd['_arm']=arm;comp=component(cd,x,entry);comp['d']=w.owner_context(cd,entry)
    npz(Path(case)/(arm+'_conditional.npz'),raw=comp['raw'],covariance=comp['covariance'],q=comp['q'],parent_coefficients=comp['parent_coefficients'],parent_noise=comp['parent_noise'])
    times=np.asarray(comp['d']['target_track']['times']);null=k.null_score(comp,np.arange(len(times)));null['independent_dense_objective']=w.null_qr(comp['raw'],comp['covariance'],times,k.PERIOD)
    null['independent_dense_error']=abs(null['objective']-null['independent_dense_objective']);null['independent_dense_passed']=bool(null['independent_dense_error']<=1e-7);null['floating_objective_allowance']=1e-6
    write(Path(case)/(arm+'_null.json'),null);threshold=-.5*(null['objective']+1e-6) if null['independent_dense_passed'] else None
    rows=[];cache={};up=sr.ecef_to_enu_matrix(*k.latlon(x))[2]
    for j,n in zip(pool,norads,strict=True):
        sr.alarm(deadline-time.monotonic());began=time.monotonic()
        try:
            candidate=k.candidate(comp['d'],n)
            if not np.array_equal(candidate['target_sky']['time_s'],candidate['target_mode_bank']['time_s']):raise ValueError('sky/mode knot mismatch')
            support=sr.sg.support(candidate['target_sky'],times,up,comp['observer']);write(Path(case)/(arm+'_'+str(n)+'_support.json'),support)
            row,fun,ip,bp=sr.score_candidate(candidate,comp,support,threshold);cache[n]=(candidate,fun,ip,bp)
            if row.get('full_support_lower_log_integral') is not None:threshold=max(threshold,row['full_support_lower_log_integral']) if threshold is not None else row['full_support_lower_log_integral']
            row.update(norad=n,candidate_index=j)
        except TimeoutError:raise
        except Exception as exc:row=dict(norad=n,candidate_index=j,status='failed',error=repr(exc),numerically_qualified=False,traceback=traceback.format_exc())
        row['seconds']=time.monotonic()-began;rows.append(row);write(Path(case)/(arm+'_'+str(n)+'_checkpoint.json'),row)
    finite=sorted([q for q in rows if q.get('objective') is not None],key=lambda q:(q['objective'],q['norad']));best=finite[0] if finite else None;diagnostic=None
    if best:
        sr.alarm(deadline-time.monotonic());diagnostic=diagnose(d,cache[best['norad']][0],comp,entry,target,best)
        write(Path(case)/(arm+'_adequacy_checkpoint.json'),dict(case=case,arm=arm,raw_best_physical=best['norad'],source_diagnostic=diagnostic,independent_references_not_yet_complete=True,identity_qualified=False))
    selected=sr.required_references(rows,null['objective'],[])
    for row in rows:
        if row['norad'] not in selected or row['norad'] not in cache:continue
        sr.alarm(deadline-time.monotonic());_,fun,ip,bp=cache[row['norad']];ref=sr.sm.reference(fun,ip);br=sr.sm.reference(fun,bp)
        err=abs(ref['objective']-row['objective']) if ref['objective'] is not None and row.get('objective') is not None else 0.
        row.update(independent_reference=ref,independent_bracket_reference=br,primary_reference_error=err)
        row['numerically_qualified'] &= bool(ref['success'] and br['success'] and err<=1e-3)
    result=dict(case=case,arm=arm,status='complete',component=target['component'],candidates=rows,null=null,evidence_order_certificate=sr.certified_order(rows,null),raw_physical_winner=best['norad'] if best else None,
        original_remaining_residual_gates_pass=info['original_remaining_gates_pass'],hard_parent_passed=True,
        source_diagnostic=diagnostic,identity_qualified=False,position_admission=False,no_new_position_fit=True,original_accepted_IDs_changed=False,
        qualification_limit='necessary residual gates and cavity evidence are not shared-parent/independent-owner identity validation')
    write(Path(case)/(arm+'_result.json'),result);return dict(case=case,arm=arm,status='complete',raw_physical_winner=result['raw_physical_winner'],order=result['evidence_order_certificate'])

def arm_worker(targets,arm,allowance):
    began=time.monotonic();out=[]
    for target in targets:
        start=time.monotonic();deadline=start+allowance
        try:
            out.append(score_owner(target,arm,deadline))
        except Exception as exc:
            fail=dict(case=target['case'],arm=arm,status='unavailable',error=repr(exc),traceback=traceback.format_exc(),physical_candidate_denominator=8)
            write(Path(target['case'])/(arm+'_failure.json'),fail);out.append(fail)
        finally:signal.setitimer(signal.ITIMER_REAL,0)
        print(arm,target['case'],out[-1]['status'],time.monotonic()-start,flush=True)
    record=dict(arm=arm,slots=out,seconds=time.monotonic()-began);write(arm+'_execution.json',record);return record

def run():
    threads();p=verify();write('execution_started.json',dict(protocol_sha256=sha(HERE/'protocol.json'),cap=CAP));began=time.monotonic();records=[]
    prefix=p['preparation_seconds']+p['test_seconds']+p['freeze_seconds']
    try:
        sr.alarm(min(90.,CAP-prefix))
        # Screening is ordinary and runs only after independent frozen approval.
        for target in p['targets']:
            case=target['case'];d=r.context(case);x=np.asarray(d['arms']['c0']['endpoint_east_north_km']);d=w.at_common_position(d,x);entry=r.read(HERE/case/'entry.json');bg={}
            for a in ARMS:
                changed,info=k.cavity(d,[],a)
                if not w.hard_parent(info):raise ValueError('screen original parent hard check failed')
                changed['_arm']=a;bg[a]=component(changed,x,entry)
            cat=w.catalogue(d,x,entry,bg['c0']['q']);npz(Path(case)/'catalogue.npz',**cat)
            for a in ARMS:
                screen=sr.previous.ordinary_screen(dict(raw_hz=bg[a]['raw'],covariance_hz2=bg[a]['covariance']),cat)
                if len(screen['candidate_indices'])!=8 or screen['forced_or_reserved_candidate']:raise ValueError('ordinary eight unforced candidates required')
                write(Path(case)/(a+'_screen.json'),screen)
        screening=time.monotonic()-began;signal.setitimer(signal.ITIMER_REAL,0);prefix+=screening
        allowance=(CAP-prefix)/8
        if allowance<=0:raise TimeoutError('no remaining score budget')
        write('screen_receipt.json',dict(seconds=screening,cumulative_prefix_seconds=prefix,owner_arm_seconds=allowance,all4ordinary_screens_frozen=True))
        with ProcessPoolExecutor(max_workers=2) as pool:
            futures={pool.submit(arm_worker,p['targets'],a,allowance):a for a in ARMS}
            for f in as_completed(futures):
                try:records.append(f.result())
                except Exception as exc:records.append(dict(arm=futures[f],seconds=allowance*4,slots=[dict(case=t['case'],status='worker_failed',error=repr(exc)) for t in p['targets']]))
    except Exception as exc:
        prefix=p['preparation_seconds']+p['test_seconds']+p['freeze_seconds']+time.monotonic()-began
        write('screening_failure.json',dict(error=repr(exc),traceback=traceback.format_exc(),cumulative_worker_seconds=prefix))
        records=[dict(arm=a,seconds=0.,slots=[dict(case=t['case'],status='screening_unavailable',error=repr(exc)) for t in p['targets']]) for a in ARMS]
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    execution=dict(arms=records,cumulative_worker_seconds=prefix+sum(q['seconds'] for q in records),wall_seconds=time.monotonic()-began,total_owner_arm_slots=8,total_candidate_slots=64,position_fits=0,GPS_used=False,operational_identity_admissions=0)
    write('execution.json',execution);verify()
    write('RF_seal.json',dict(files={str(f):sha(f) for f in sorted(HERE.rglob('*')) if f.is_file() and '__pycache__' not in f.parts and '.pytest_cache' not in f.parts},protocol_sha256=sha(HERE/'protocol.json'),position_fits=0,GPS_used=False))
    print('TERMINAL',execution['cumulative_worker_seconds'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);a=parser.parse_args();globals()[a.action]()
