"""Ten distinct causal localization prototypes, preserving incumbent evidence."""
import argparse,copy,hashlib,json,sys,time,warnings
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy.optimize import root, minimize

OUT=Path(__file__).resolve().parent
PREVIOUS=OUT.parent/'2026_11_01_ds26_solution_prototypes'
sys.path.insert(1,str(PREVIOUS))
import prototype as previous
from prototype import INPUT,PRIOR,CASES,ARMS,SUSPECT,read,write,reconstruct,objective
from ds23_frequency_events import make_event_problem,attach_event_predictive
import ds23_frequency_events as events_module
import predictive_new_family as mixture_module
from ds23_height_problem import geometry_features as ORIGINAL_GEOMETRY
from probe_ds23_frequency_events import cached
from probe_ds23_history_calibrated_phase import make_problem
from dsx01_joint_marginal import JointMarginal
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_receiver_smooth_prior import scale_posterior
from phase_reference_checks import phase_refresh
from probe_algo03_feasible_recovery import gate_slacks
from ds23_feasible_position import feasible_fit

METHODS={
 '01_damped_phase':'Half-step phase refresh to suppress oscillation',
 '02_inner_phase':'Solve phase consistency inside each position evaluation',
 '03_regional_basins':'RF-ranked regional multistart across the 25 km box',
 '04_receiver_shrink':'Reduce nonlinear receiver smooth prior SD 200 to 50 Hz',
 '05_orbit_shrink':'Halve all physical orbital-mode prior standard deviations',
 '06_age_uncertainty':'Add independent phase uncertainty of one second per 24 h TLE age in quadrature',
 '07_shared_rate':'Add one Gaussian satellite-shared frequency rate, SD 0.5 Hz/s',
 '08_fragment_partition':'RF-nominated whole-graph-track identity partition',
 '09_joint_families':'Joint replacement of primary and a conflicting/influential secondary family',
 '10_gate_margin':'Constrained fit with 0.05 normalized slack margin',
}
ORIGINAL_BUILD=previous.build
ORIGINAL_REFRESH=previous.phase_refresh
ORIGINAL_FEASIBLE=previous.feasible_fit
ORIGINAL_MEMBERSHIPS=previous.memberships
ORIGINAL_EVENT_DESIGN=events_module.event_design

def context_starts(d,case):
    n=SUSPECT[case];f=PRIOR/case/f'extended_omit_{n}.json'
    if not f.exists():f=PRIOR/case/f'omit_{n}.json'
    return {'published':np.asarray(d['problems']['fitted_c'][1]),'family_omitted':np.asarray(read(f)['fitted_c']['x'])}

def prior_factory(base_factory,method):
    def factory(scan,node,keep,arm,reference,weights,means,multiplier,nu):
        p=base_factory(scan,node,keep,arm,reference,weights,means,multiplier,nu)
        if method=='06_age_uncertainty':
            cutoff=scan.receipt['cutoff_utc_ns'];age=[]
            for j in p.labels:
                v=scan.elements[str(int(scan.norads[j]))]['provenance'];epoch=v['element_epoch_utc_ns']
                if epoch>cutoff or v['collected_utc_ns']>cutoff:raise ValueError('noncausal element')
                age.append((cutoff-epoch)/3.6e12)
            p.phase_sigma=np.hypot(p.phase_sigma,np.asarray(age)/24)
        begin=p.hardware.shape[1]+p.smooth.shape[1]
        width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
        mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
        scales=np.ones(width);scales[-len(p.members):]=.3
        if method=='04_receiver_shrink':scales[p.hardware.shape[1]:begin]=.25
        if method=='05_orbit_shrink':scales[begin+len(p.labels):begin+len(p.labels)+3*len(p.supported)]=.5
        groups=np.full(width,-1,int)
        if nu is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
        def calculate(x):
            result=JointMarginal.calculate(p,x);features=result['features'];raw=p.values-p.q*result['intercept']-features@mean
            present=np.unique(p.noise_groups[keep])
            bound=hierarchical_bound(raw[keep],(features*scales)[keep],p.point_noise[keep],p.noise_groups[keep],powers=np.asarray(weights)[present],
                prior_groups=None if nu is None else groups,prior_nu=4 if nu is None else nu)
            bound=scale_posterior(bound,scales);bound['latent_coefficient']=bound['coefficient'].copy();bound['coefficient']+=mean
            precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
            bound['conditional_residual_hz']=p.values-p.q*result['intercept']-features@bound['coefficient']
            volume=float(2*np.sum(np.asarray(weights)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
            bound['residual']=np.r_[bound['residual'],np.sqrt(volume)];result.update(bound);return result
        p.calculate=calculate;return p
    return factory

def centered_event_design(times,receivers,channels,rf_hz,labels,events):
    result=ORIGINAL_EVENT_DESIGN(times,receivers,channels,rf_hz,labels,events)
    for k,event in enumerate(events):
        if event.get('centered_rate'):
            # On the recorded 0..300 s interval, this is exactly 0.5*(t-150).
            result[:,k]-=.5*event['sigma_hz']*(np.asarray(labels)==event['candidate_index'])*np.asarray(rf_hz)/11.5e9
    return result

def event_geometry(view,x,height=0.):
    result=ORIGINAL_GEOMETRY(view,x,height)
    if getattr(view,'events',[]):
        if any(e['kind']!='family' for e in view.events):raise ValueError('only satellite events supported here')
        labels=np.asarray(view.labels)[view.flat_labels];zeros=np.zeros(len(view.flat_times),int)
        design=centered_event_design(view.flat_times,zeros,zeros,view.q*11.5e9,labels,view.events)
        result=dict(result,features=np.column_stack((result['features'],design)))
    return result

def conditional_with_events(p,entries,powers,families):
    from conditional_satellite_refresh import family_coordinates,conditional_update
    from ds23_predictive_linear import linear_geometry
    indices=family_coordinates(p,families);begin=p.hardware.shape[1]+p.smooth.shape[1]
    view,values,sigma,groups,slices=linear_geometry(p,entries);curved=p.curved_calculate
    def calculate(x):
        base=curved(x);c=dict(base);geometry=event_geometry(view,x,0.);h=geometry['features']
        g=p.noise_groups[p.keep];w=np.asarray(powers)[g]*base['noise_precision'][g]/p.point_noise[p.keep]**2
        u=base['features'][p.keep];gram=np.diag(base['coefficient_prior_precision'])+u.T@(u*w[:,None])
        raw=values-view.q*geometry['intercept']-h@base['coefficient']
        delta,prediction,distance=conditional_update(base['coefficient'],gram,h,raw,sigma,groups,indices)
        c.update(coefficient=base['coefficient']+delta,latent_coefficient=base['latent_coefficient']+delta,
            conditional_residual_hz=base['conditional_residual_hz']-base['features']@delta,
            linear_raw_prediction_residual_hz=raw-h@delta,linear_elevation=geometry['elevation'],
            curved_negative_twice_elbo=base['negative_twice_elbo'],linear_predictive_objective=prediction['objective'],
            negative_twice_elbo=base['negative_twice_elbo']+prediction['objective'],
            normalization_constant=base['normalization_constant']+prediction['normalization_constant'],
            residual=np.r_[base['residual'],prediction['residual']],shared_satellite_receiver_change=float(np.max(abs(delta[:begin]))),
            shared_satellite_coefficient_change=delta,shared_satellite_allowed_coordinates=indices,conditional_satellite_shift_mahalanobis=distance)
        return c
    p.calculate=calculate;p.shared_satellite_families=sorted(set(families));return p

def event_memberships(p,x,entries):
    from audit_ds23_algo01_coverage import retained_metrics
    from ds23_frequency_events import extend_event_associations
    curved={o for i,sl in zip(p.members,p.slices) for o,use in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl]) if use}
    predictive={o for e in entries for o in e['observation_ids']};owners={};lookup={t['key']:t for t in p.scan.tracks}
    for r in extend_event_associations(p,x,retained_metrics(p,x))['tracks']:
        if not r['compatible']:continue
        ids=r.get('observation_ids',lookup[r['component']]['observation_ids'])
        if set(ids)&predictive:continue
        owners.update({o:r['norad'] for o in ids})
    for e in entries:owners.update({o:e['norad'] for o in e['observation_ids']})
    return curved,predictive,curved|predictive|set(owners),owners

def builder(method,rate_norad=None):
    def build(d,z,arm,reference,*args,**kwargs):
        if args or kwargs:raise ValueError('no omissions or hidden phase scaling in new trials')
        factory=d.get('problem_factory',make_problem)
        if method in ('04_receiver_shrink','05_orbit_shrink','06_age_uncertainty'):factory=prior_factory(factory,method)
        events=[]
        if method=='07_shared_rate':
            j=list(d['scan'].norads).index(rate_norad)
            events=[dict(kind='family',candidate_index=j,time_s=0.,transition_s=300.,sigma_hz=150.,centered_rate=True)]
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(reference),d['powers'],d['means'],d['model'],events,base_problem_factory=factory)
        attach_event_predictive(p,d['entries'],d['powers'])
        if z['gap_selected']:
            from conditional_satellite_refresh import attach_conditional_satellite_refresh
            protocol=read(Path(z['gap_selected']['path'])/'protocol.json')
            attach=conditional_with_events if events else attach_conditional_satellite_refresh
            attach(p,d['entries'],d['powers'],[e['candidate_index'] for e in protocol['targets']])
        return cached(p),d
    return build

def configure(method,n):
    previous.build=builder(method,n)
    previous.phase_refresh=ORIGINAL_REFRESH
    previous.feasible_fit=ORIGINAL_FEASIBLE
    previous.memberships=ORIGINAL_MEMBERSHIPS
    events_module.event_design=ORIGINAL_EVENT_DESIGN
    mixture_module.geometry_features=ORIGINAL_GEOMETRY
    if method=='01_damped_phase':
        def damped(phases,reference,limit_s=30):
            updated,check=ORIGINAL_REFRESH(phases,reference,limit_s)
            return .5*np.asarray(reference)+.5*updated,check
        previous.phase_refresh=damped
    if method=='10_gate_margin':
        def margin(fun,slacks,*args,**kw):return ORIGINAL_FEASIBLE(fun,lambda x:np.asarray(slacks(x))-.05,*args,**kw)
        previous.feasible_fit=margin
    if method=='07_shared_rate':
        events_module.event_design=centered_event_design;previous.memberships=event_memberships
        mixture_module.geometry_features=event_geometry

def compact(r,d,z,arm,allowed):
    original=z['baseline_owners'][arm]
    unexpected=[o for o in r['reassigned_ids'] if original[o] not in allowed]
    r['unexpected_reassigned_ids']=unexpected;r['qualified'] &= not unexpected
    r['owners_sha256']=hashlib.sha256(json.dumps(r.pop('proposed_owners'),sort_keys=True).encode()).hexdigest()
    native=[o for t in r['tracks'] for o in t['observation_ids']]
    assert len(native)==len(set(native))==r['active_points']
    r['native_fit_ids_sha256']=hashlib.sha256('\n'.join(sorted(native)).encode()).hexdigest()
    # Keep residual evidence for touched families; retain aggregate checks for all others.
    r['tracks']=[t for t in r['tracks'] if t['norad'] in allowed]
    p,dd=previous.build(d,z,arm,np.asarray(r['reference']));x=np.asarray(r['x']);slacks=gate_slacks(p,x,dd['entries'])
    r['minimum_gate_slack']=float(min(slacks.values()))
    if getattr(p,'events',[]):r['event_amplitudes_hz']=p.calculate(x)['event_amplitudes_hz']
    return r

def inner_fit(d,z,arm,start):
    """Nested phase fixed point: deterministic inner seed, bounded root solve."""
    reference=d['problems'][arm][0].reference.copy();cache={};tic=time.monotonic();evaluations=[]
    def evaluate(x):
        if time.monotonic()-tic>45:raise TimeoutError('45-second nested-solver cap')
        key=tuple(np.asarray(x,float))
        if key in cache:return cache[key]
        def residual(ref):
            if time.monotonic()-tic>45:raise TimeoutError('45-second nested-solver cap')
            p,_=previous.build(d,z,arm,np.clip(ref,-30,30))
            return p.state(x)['phases'][p.labels]-ref
        sol=root(residual,reference,method='hybr',options=dict(maxfev=60,eps=1e-4,xtol=1e-5))
        ref=np.clip(sol.x,-30,30);p,dd=previous.build(d,z,arm,ref);change=float(max(abs(p.state(x)['phases'][p.labels]-ref)))
        gates=gate_slacks(p,x,dd['entries']);gates['inner_closure']=.01-change
        cost=objective(p,dd,x)+1e4*max(0,change-.01)**2
        result=dict(cost=cost,slacks=list(gates.values()),reference=ref,change=change,x=np.asarray(x));cache[key]=result
        evaluations.append(dict(x=x,phase_change_s=change,inner_success=bool(sol.success),nfev=int(sol.nfev)))
        return result
    opt=feasible_fit(lambda x:evaluate(x)['cost'],lambda x:evaluate(x)['slacks'],start,[-12.5]*2,[12.5]*2,iterations=20)
    final=evaluate(opt['parameters']);dd=dict(d,problems=dict(d['problems']))
    p,_=previous.build(d,z,arm,final['reference']);dd['problems'][arm]=(p,np.asarray(opt['parameters']))
    saved=previous.feasible_fit
    previous.feasible_fit=lambda *args,**kw:dict(parameters=opt['parameters'],solver_success=opt['solver_success'],solver_message='fixed endpoint audit after nested solve',evaluations=0)
    try:r=previous.fit(dd,z,arm,np.asarray(opt['parameters']),True,rounds=1)
    finally:previous.feasible_fit=saved
    r.update(nested_evaluations=evaluations,seconds=time.monotonic()-tic);return r

def run(case,method):
    out=OUT/case/method;out.mkdir(parents=True,exist_ok=True);z=read(INPUT/(case+'.json'));d=reconstruct(z)
    starts=context_starts(d,case);plan=read(OUT/case/'plan.json');hypotheses=plan['hypotheses'].get(method,plan['whole_hypotheses'])
    write(out/'replay.json',d['replay_checks'])
    for h in hypotheses:
        target=out/(h['name']+'.json')
        if target.exists():continue
        # Context assembly must use the untouched previous builder.
        previous.build=ORIGINAL_BUILD
        dd=remap(d,z,case,h) if 'mapping' in h else previous.candidate(d,z,case,h['norad'],1.)
        configure(method,h.get('norad',SUSPECT[case]));trial_starts=dict(starts)
        if method=='03_regional_basins':
            scores=[]
            for east in (-12.5,0.,12.5):
                for north in (-12.5,0.,12.5):
                    x=np.array([east,north]);score=0.
                    for a in ARMS:
                        p,ctx=previous.build(dd,z,a,dd['problems'][a][0].reference);score+=objective(p,ctx,x)
                    scores.append((score,east,north))
            for k,(_,e,n) in enumerate(sorted(scores)[:2]):trial_starts['regional_'+str(k)]=np.array([e,n])
        rows=[]
        for arm in ARMS:
            for name,start in trial_starts.items():
                try:
                    r=inner_fit(dd,z,arm,start) if method=='02_inner_phase' else previous.fit(dd,z,arm,start,True,rounds=15)
                    r=compact(r,dd,z,arm,set(h.get('allowed_families',[SUSPECT[case],h['norad']])))
                    if method=='10_gate_margin':r['qualified'] &= r['minimum_gate_slack']>=.05-1e-5
                    r.update(status='complete',arm=arm,start=name,complexity_penalty=h.get('penalty',0.),ranking_score=r['objective']+h.get('penalty',0.))
                    print(case,method,h['name'],arm,name,round(r['error_m']/1000,3),r['qualified'],flush=True)
                except Exception as exc:
                    r=dict(status='incomplete',arm=arm,start=name,exception=type(exc).__name__,reason=str(exc),qualified=False)
                    print(case,method,h['name'],arm,name,type(exc).__name__,str(exc)[:160],flush=True)
                rows.append(r)
        write(target,dict(case=case,method=method,hypothesis=h,rows=rows))

def remap(d,z,case,h):
    """Apply per-source hypotheses, preserving native masks and other owners."""
    from sgp4.api import Satrec
    from leo.sky.propagation import ElementSetCatalogue
    from analyze_dsx01_fixed_site import ecef_states
    dd=dict(d,node=copy.deepcopy(d['node']),entries=copy.deepcopy(d['entries']),problems={})
    scan=copy.copy(d['scan']);dd['scan']=scan;ledger=read(PRIOR/case/'tle-ledger.json')['causal'];base=d['problems']['fitted_c'][0]
    for n in sorted(set(h['mapping'].values())):
        if n in scan.norads:continue
        record=ledger[str(n)];cat=ElementSetCatalogue((str(n),),(n,),(Satrec.twoline2rv(*record['lines']),))
        pos,vel,good=ecef_states(cat,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
        if not good.all():raise ValueError('causal candidate propagation failed')
        scan.norads=np.r_[scan.norads,n];scan.sky=dict(scan.sky,position_km=np.concatenate([scan.sky['position_km'],pos]),velocity_km_s=np.concatenate([scan.sky['velocity_km_s'],vel]),phase_sigma_s=np.r_[scan.sky['phase_sigma_s'],1.])
        scan.elements=dict(scan.elements,**{str(n):dict(lines=record['lines'],provenance={k:v for k,v in record.items() if k!='lines'})})
        dd['node']['seed']['state']['phases']=np.r_[dd['node']['seed']['state']['phases'],0.]
    for row in dd['node']['seed']['rows']:
        key=row['component']
        if key in h['mapping']:
            n=h['mapping'][key];row.update(candidate_norad=n,candidate_index=list(scan.norads).index(n))
    for k,row in enumerate(base.rows):
        if row['component'] in h['aliases']:dd['node']['aliases'][k]=h['aliases'][row['component']]
    family_destinations={}
    for row in base.rows:
        family_destinations.setdefault(row['candidate_norad'],set()).add(h['mapping'].get(row['component'],row['candidate_norad']))
    for e in dd['entries']:
        if e['component'] in h['mapping']:
            e['norad']=h['mapping'][e['component']];e['candidate_index']=list(scan.norads).index(e['norad'])
        elif len(family_destinations.get(e['norad'],set()))==1:
            e['norad']=next(iter(family_destinations[e['norad']]));e['candidate_index']=list(scan.norads).index(e['norad'])
    labels=sorted({r['candidate_index'] for r in dd['node']['seed']['rows']});oldmeans=dict(zip(base.labels,d['means']))
    dd['means']=np.array([oldmeans.get(j,0.) for j in labels])
    for a in ARMS:
        old,x=d['problems'][a];refs=dict(zip(old.labels,old.reference));ref=np.array([refs.get(j,h['phases'].get(str(int(scan.norads[j])),0.)) for j in labels])
        dd['problems'][a]=(old,x);p,_=ORIGINAL_BUILD(dd,z,a,ref);dd['problems'][a]=(p,x)
    return dd

def prepare(case):
    """Freeze all proposals before evaluating any new method against truth."""
    from track_debug import bank_for,fit_candidates
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.retained_track_likelihood import PERIOD
    from prototype_dsx01_continuous_position import latlon
    z=read(INPUT/(case+'.json'));d=reconstruct(z);base,x=d['problems']['fitted_c'];old=SUSPECT[case]
    nums=previous.nominees(case);whole=[dict(name=str(n),norad=n) for n in nums]
    f=read(PRIOR/case/'family_diagnostic.json');records={}
    for n in nums:
        records[n]={a:next(r for r in f['results'] if r['norad']==n and r['arm']==a and r['regime']=='causal' and r['calibration']=='family_omitted' and r['level']=='small_rate' and r['split']=='all') for a in ARMS}
    mapping={};aliases={};phases={};partition_costs=[]
    for k,t in enumerate(f['tracks']):
        costs={n:sum(records[n][a]['per_track'][k]['rms_hz']**2*len(t['times_s'])/150**2 for a in ARMS) for n in nums}
        winner=min(costs,key=costs.get);mapping[t['key']]=winner;aliases[t['key']]=int(records[winner]['fitted_c']['aliases'][k]);phases[str(winner)]=records[winner]['fitted_c']['phase_s']
        partition_costs.append(dict(component=t['key'],paired_costs=costs,winner=winner))
    extra=max(0,len(set(mapping.values()))-1)
    partition=dict(name='rf_fragment_partition',mapping=mapping,aliases=aliases,phases=phases,norad=old,
        allowed_families=sorted(set(nums)),penalty=2*extra*np.log(sum(len(t['times_s']) for t in f['tracks'])),proposal='whole-track pooled RF costs; shared phase/rate nominee, no evaluation truth')
    # Reuse the lowest-RF full-weight primary hypothesis, even if rejected, to
    # identify the actual incumbent it conflicts with.
    candidates=[]
    for path in (PREVIOUS/case).glob('*-w1-free.json'):
        trial=read(path)
        for r in trial['rows']:
            if r['arm']=='fitted_c':candidates.append((r['objective'],trial['new_norad'],r))
    _,primary,saved=min(candidates,key=lambda v:v[0]);dd=previous.candidate(d,z,case,primary,1.)
    p,_=ORIGINAL_BUILD(dd,z,'fitted_c',np.array(saved['reference']));point=np.array(saved['x'])
    secondary=None
    for key,val in sorted(saved['failed_gates'].items(),key=lambda kv:kv[1]):
        row=next((r for r in p.rows if key.startswith(r['component']+'/') and r['candidate_norad']!=primary),None)
        if row:secondary=row['candidate_norad'];break
    if secondary is None:
        audit=read(PRIOR/case/'audit.json');rank={}
        for a in ARMS:
            for r in audit['arms'][a]['family_influence']:
                if r['norad']!=old:rank[r['norad']]=rank.get(r['norad'],0)+r['shift_norm_km']
        secondary=max(rank,key=rank.get)
    tracks=[(int(p.keep[sl].sum()),i,sl) for r,i,sl in zip(p.rows,p.members,p.slices) if r['candidate_norad']==secondary and p.keep[sl].any()]
    _,i,sl=max(tracks);t=d['scan'].tracks[i];use=p.keep[sl];state=p.state(point)
    calibration=d['scan'].hardware(t,state['beta'])+t['rf_hz']/11.5e9*d['scan'].rx_basis[i]@state['smooth'][t['receiver']-1]
    ledger=read(PRIOR/case/'tle-ledger.json')['causal'];allnums,bank,failed=bank_for(ledger,z['scan_receipt']['origin_utc_ns'])
    guesses=fit_candidates(t['times'][use],(t['values']-calibration)[use],t['rf_hz']/11.5e9,allnums,bank,point,secondary,float(state['phases'][list(p.scan.norads).index(secondary)]))
    shortlist=sorted([r for r in guesses if r['model']=='L3_phase' and r['norad']!=secondary],key=lambda r:r['score'])[:2]
    joint=[]
    for rank,g in enumerate(shortlist):
        new=g['norad'];mp={};al={};ph={str(primary):float(state['phases'][list(p.scan.norads).index(primary)]),str(new):g['phase_s']}
        for k,(row,idx,span) in enumerate(zip(p.rows,p.members,p.slices)):
            if row['candidate_norad']==primary and d['problems']['fitted_c'][0].rows[k]['candidate_norad']==old:
                mp[row['component']]=primary;al[row['component']]=int(p.alias[k])
            if row['candidate_norad']!=secondary:continue
            tr=d['scan'].tracks[idx];j=int(np.flatnonzero(allnums==new)[0]);bb=dict(time_s=bank['time_s'],position_km=bank['position_km'][[j]],velocity_km_s=bank['velocity_km_s'][[j]])
            orbit,_=paired_phase_frequency(bb,tr['times'],np.zeros(len(tr['times']),int),np.array([g['phase_s']]),*latlon(point))
            radio=d['scan'].hardware(tr,state['beta'])+tr['rf_hz']/11.5e9*d['scan'].rx_basis[idx]@state['smooth'][tr['receiver']-1]
            raw=tr['values']-radio-tr['rf_hz']/11.5e9*orbit
            mp[row['component']]=new;al[row['component']]=int(np.rint(-np.mean(raw[p.keep[span]])/PERIOD)) if p.keep[span].any() else int(p.alias[k])
        joint.append(dict(name=f'{primary}_{secondary}_to_{new}',norad=primary,mapping=mp,aliases=al,phases=ph,allowed_families=[old,primary,secondary,new],penalty=2*np.log(max(2,len(shortlist))),proposal='replace primary plus RF-conflicting secondary; causal shortlist from longest secondary source'))
    write(OUT/case/'plan.json',dict(case=case,whole_hypotheses=whole,hypotheses={'08_fragment_partition':[partition],'09_joint_families':joint},partition_costs=partition_costs,
        secondary_nomination=dict(primary=primary,secondary=secondary,component=t['key'],catalogue_size=len(allnums),propagation_failures=failed,
            nominees=[{k:v for k,v in r.items() if not isinstance(v,(np.ndarray,list,dict))} for r in shortlist]),
        observations_preserved=True,GPS_used_for_proposals=False))
    print(case,'prepared',len(nums),'whole identities; secondary',secondary,'nominees',[r['norad'] for r in shortlist],flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('case');a.add_argument('method',choices=['prepare']+list(METHODS));args=a.parse_args()
    prepare(args.case) if args.method=='prepare' else run(args.case,args.method)
