"""RF-triggered incumbent reconsideration; bounded research, no production writes.

Truth is used only by the imported endpoint reporter. Candidate proposals,
splits, ranking and acceptance below do not use position error.
"""
import argparse, copy, hashlib, json, sys, time
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent/'2026_11_01_ds26_ten_solutions'))
import experiment as ex
from experiment import previous, read, write, reconstruct, INPUT, ARMS
from diagnose import build, derivatives, objective, refit
from track_debug import bank_for
from predictive_check import fit_predict
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from prototype_dsx01_continuous_position import latlon

DEVELOP=['DS26-0203','DS26-0070','DS26-0251','DS26-0034']
CATALOGUES=INPUT.parent/'catalogues'
SEED=20261103

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def freeze():
    rng=np.random.default_rng(SEED); validation=[]
    for cohort in ('DS26','DS27'):
        names=sorted(p.stem for p in INPUT.glob(cohort+'-*.json') if p.stem not in DEVELOP)
        validation+=list(rng.choice(names,4,replace=False))
    write(OUT/'protocol.json',dict(seed=SEED,development=DEVELOP,validation=validation,
        source_sha256=sha(__file__),input_sha256={c:sha(INPUT/(c+'.json')) for c in DEVELOP+validation},
        trigger='top two curved families by summed c-arm finite-difference local omission displacement; >=0.5 km; >=30 native fitted points and >=2 tracks',
        catalogue='complete existing 72h causal regional bank, epoch and collection checked; latest per identity; no later TLEs',
        nomination='two longest active family tracks; <=16 uniform samples, phase -30..30 by2s; top2 per track/arm, union with incumbent',
        family_model='frozen family-omitted radio and position; native points; per-source offset300Hz, one shared rate0.5Hz/s, noise150Hz, phaseSD5s; phase grid0.4s',
        folds=5,block_seconds=5,guard_seconds=5,held_fraction=.2,
        predictive_accept='mean held score gain>0 and >=4/5 positive folds in each c arm; conditional on full-data nomination and graph tracks',
        proposals='top two whole-family nominees by summed full RF scores plus an >=80%-stable whole-track partition; no hypothesis chosen by error',
        phase_rounds=15,position_iterations=40,starts='same published fitted-c and fitted-c family-omitted endpoints in both arms',
        position_box_km=25,center=[37.906,-122.545],
        acceptance='paired RF improvement beyond 2log(number searched nominees), existing gates/exact orbit/phase closure/solver/no owners lost/no unintended reassignment + conditional predictive check',
        limit='one family modification per scan; all nominated families tested from original baseline, no greedy chaining',
        validation_scope='additional random scans, not previously untouched datasets; rule frozen before these outcomes',production_changed=False))

def rank_families(d,z):
    rows={}
    for a,(p,x) in d['problems'].items():
        g,H=derivatives(lambda v:objective(p,d,v),x)
        for n in sorted({r['candidate_norad'] for r,s in zip(p.rows,p.slices) if p.keep[s].any()}):
            q,dd=build(d,z,a,p.reference,omit=n)
            go,_=derivatives(lambda v:objective(q,dd,v),x)
            displacement=float(np.linalg.norm(np.linalg.pinv(H)@(go-g)))
            entries=[(r,s) for r,s in zip(p.rows,p.slices) if r['candidate_norad']==n and p.keep[s].any()]
            item=rows.setdefault(n,dict(norad=n,rank_score=0.,arms={},points=sum(int(p.keep[s].sum()) for r,s in entries),tracks=len(entries)))
            item['arms'][a]=dict(local_displacement_km=displacement,hessian_eigenvalues=np.linalg.eigvalsh(H))
            item['rank_score']+=displacement
    result=sorted(rows.values(),key=lambda r:(-r['rank_score'],r['norad']))
    selected=[r['norad'] for r in result if r['rank_score']>=.5 and r['points']>=30 and r['tracks']>=2][:2]
    return result,selected

def masks(times,groups,unique=False):
    blocks=np.floor(times/5).astype(int);available=np.unique(blocks);rng=np.random.default_rng(SEED);result=[]
    seen=set()
    for fold in range(5):
        for retry in range(2000):
            held=np.sort(rng.choice(available,max(1,round(.2*len(available))),replace=False))
            if unique and tuple(held) in seen:continue
            test=np.isin(blocks,held);train=~np.isin(blocks,np.r_[held-1,held,held+1])
            if all(sum(train&(groups==g))>=5 and sum(test&(groups==g))>=2 for g in np.unique(groups)):break
        else:return []
        seen.add(tuple(held))
        result.append(dict(fold=fold,train=train,test=test,held_blocks=held,retries=retry))
    return result

def causal_records(case,z):
    ledger=read(CATALOGUES/(case+'.json'))['elements'];cutoff=z['scan_receipt']['cutoff_utc_ns']
    for r in ledger.values():
        age=(cutoff-r['element_epoch_utc_ns'])/3.6e12
        if not (0<=age<=72 and r['collected_utc_ns']<=cutoff):raise ValueError('noncausal or too old catalogue')
    return ledger

def screen(d,z,n,nums,bank,out):
    base=d['problems']['fitted_c'][0]
    tracks=[(i,base.keep[s]) for r,i,s in zip(base.rows,base.members,base.slices) if r['candidate_norad']==n and base.keep[s].any()]
    ts=np.concatenate([d['scan'].tracks[i]['times'][use] for i,use in tracks])
    q=np.concatenate([np.full(sum(use),d['scan'].tracks[i]['rf_hz']/11.5e9) for i,use in tracks])
    groups=np.concatenate([np.full(sum(use),k) for k,(i,use) in enumerate(tracks)])
    parts=masks(ts,groups); pp=np.linspace(-30,30,151);cavity={};values={};nominees={n};coarse=[]
    longest=sorted(range(len(tracks)),key=lambda k:-sum(tracks[k][1]))[:2]
    for a in ARMS:
        cav=refit(d,z,a,d['problems']['fitted_c'][1],omit=n,rounds=15);cavity[a]=cav
        p,_=build(d,z,a,np.array(cav['reference']),omit=n);x=np.array(cav['x']);state=p.state(x)
        values[a]=np.concatenate([(tr['values']-p.scan.hardware(tr,state['beta'])-tr['rf_hz']/11.5e9*p.scan.rx_basis[i]@state['smooth'][tr['receiver']-1])[use] for i,use in tracks for tr in [p.scan.tracks[i]]])
        for k in longest:
            ii=np.flatnonzero(groups==k);ii=ii[np.unique(np.linspace(0,len(ii)-1,min(16,len(ii))).astype(int))]
            best=np.full(len(nums),np.inf)
            for phi in np.arange(-30,31,2):
                f,e=phase_frequency_grid(bank,ts[ii],*latlon(x),phase_seconds=phi)
                cost=profile_rate(values[a][ii],f*q[ii],ts[ii],rate_sigma_hz_s=.5,bias_sigma_hz=300)['cost']+(phi/5)**2
                best=np.minimum(best,np.where(e.min(axis=1)>=0,cost,np.inf))
            finalists=[int(j) for j in np.argsort(best)[:2] if np.isfinite(best[j])];nominees.update(int(nums[j]) for j in finalists)
            coarse.append(dict(arm=a,track=d['scan'].tracks[tracks[k][0]]['key'],nominees=[dict(norad=int(nums[j]),score=float(best[j])) for j in finalists]))
    raw={};whole={};folds=[]
    for a in ARMS:
        raw[a]={};whole[a]={}
        for v in sorted(nominees):
            j=int(np.flatnonzero(nums==v)[0]);bb=dict(time_s=bank['time_s'],position_km=np.broadcast_to(bank['position_km'][j],(len(pp),*bank['position_km'][j].shape)),velocity_km_s=np.broadcast_to(bank['velocity_km_s'][j],(len(pp),*bank['velocity_km_s'][j].shape)))
            f,e=paired_phase_frequency(bb,np.tile(ts,len(pp)),np.repeat(np.arange(len(pp)),len(ts)),pp,*latlon(np.array(cavity[a]['x'])))
            # All shortlisted family hypotheses must be visible over every source
            # at every phase in this reduced predictive check; conservative scope.
            if np.min(e)<0:continue
            raw[a][v]=values[a][None,:]-f.reshape(len(pp),-1)*q
            whole[a][v]=fit_predict(raw[a][v],ts,q,groups,np.ones(len(ts),bool),np.ones(len(ts),bool),pp)
    common=sorted(set(raw['c0'])&set(raw['fitted_c']))
    if n not in common:return dict(status='incumbent_not_visible_over_complete_phase_grid',cavity=cavity,coarse=coarse,nominees=common)
    for part in parts:
        for a in ARMS:
            fitted={v:fit_predict(raw[a][v],ts,q,groups,part['train'],part['test'],pp) for v in common}
            folds.append(dict(arm=a,fold=part['fold'],fits=fitted))
    ranked=sorted([v for v in common if v!=n],key=lambda v:sum(whole[a][v]['training_score'] for a in ARMS))[:2]
    proposals=[]
    def predictive_ok(v):
        results={}
        for a in ARMS:
            gains=[r['fits'][n]['predictive_score']-r['fits'][v]['predictive_score'] for r in folds if r['arm']==a]
            results[a]=dict(gains=gains,mean=float(np.mean(gains)) if gains else None,wins=sum(g>0 for g in gains),pass_check=len(gains)==5 and np.mean(gains)>0 and sum(g>0 for g in gains)>=4)
        return results
    keys=[d['scan'].tracks[i]['key'] for i,u in tracks]
    for v in ranked:
        proposals.append(dict(name=f'{n}_to_{v}',norad=v,mapping=dict.fromkeys(keys,v),aliases={key:whole['fitted_c'][v]['alias_by_group'][k] for k,key in enumerate(keys)},
            phases={str(v):whole['fitted_c'][v]['phase_map_s']},allowed_families=[n,v],predictive=predictive_ok(v),penalty=float(2*np.log(max(2,len(common))))))
    # Partial partition proposal keeps unstable whole tracks on their incumbent.
    mapping={};stability=[]
    for k,key in enumerate(keys):
        winners=[min(common,key=lambda v:r['fits'][v]['training_track_cost'][k]) for r in folds]
        counts={v:winners.count(v) for v in common};win=max(common,key=lambda v:counts[v])
        stable=bool(len(winners)==10 and all(sum(min(common,key=lambda v:r['fits'][v]['training_track_cost'][k])==win for r in folds if r['arm']==a)>=4 for a in ARMS))
        mapping[key]=win if stable else n;stability.append(dict(component=key,counts=counts,stable=stable,label=mapping[key]))
    if len(set(mapping.values()))>1:
        predictive={};phases={};aliases={};partition_results=[]
        for a in ARMS:
            gains=[]
            for part in parts:
                score=0.
                for v in set(mapping.values()):
                    mask=np.isin(groups,[k for k,key in enumerate(keys) if mapping[key]==v])
                    r=fit_predict(raw[a][v][:,mask],ts[mask],q[mask],groups[mask],part['train'][mask],part['test'][mask],pp);score+=r['predictive_score']
                original=next(r for r in folds if r['arm']==a and r['fold']==part['fold'])['fits'][n]['predictive_score'];gains.append(original-score)
            predictive[a]=dict(gains=gains,mean=float(np.mean(gains)) if gains else None,wins=sum(g>0 for g in gains),pass_check=len(gains)==5 and np.mean(gains)>0 and sum(g>0 for g in gains)>=4)
        for v in set(mapping.values()):
            mask=np.isin(groups,[k for k,key in enumerate(keys) if mapping[key]==v]);r=fit_predict(raw['fitted_c'][v][:,mask],ts[mask],q[mask],groups[mask],np.ones(sum(mask),bool),np.ones(sum(mask),bool),pp)
            phases[str(v)]=r['phase_map_s'];aliases.update({keys[k]:alias for k,alias in r['alias_by_group'].items()})
        proposals.append(dict(name=f'{n}_stable_partition',norad=n,mapping=mapping,aliases=aliases,phases=phases,allowed_families=sorted(set(mapping.values())|{n}),predictive=predictive,
            penalty=float(2*np.log(max(2,len(common)))+2*(len(set(mapping.values()))-1)*np.log(len(ts))),
            prediction_limit='mapping selected across these same folds; development diagnostic, cannot meet independent predictive acceptance'))
    result=dict(status='screened',cavity=cavity,coarse=coarse,nominees=common,whole=whole,folds=folds,partitions=parts,proposals=proposals,stability=stability,
        points=len(ts),tracks=keys,scope='conditional prediction with family-omitted position/calibration; discovery uses full family data')
    write(out/'screen.json',result);return result

def extend_history(d,z,case,new_ids,out):
    """Apply the existing previous-TLE policy to newly admitted identities too."""
    import subprocess
    new_ids={int(n) for n in new_ids if int(n) not in d['scan'].norads}
    if not new_ids:return d,{}
    ledger=causal_records(case,z);cutoff=z['scan_receipt']['cutoff_utc_ns']
    request=dict(cutoff=cutoff,latest={str(n):ledger[str(n)]['element_epoch_utc_ns'] for n in new_ids})
    # The service archive is readable only by root. This isolated helper only
    # reads the archive and returns selected historical elements on stdout.
    result=subprocess.run(['sudo','-n','env','PYTHONDONTWRITEBYTECODE=1','PYTHONPATH='+str(OUT.parents[1]/'src'),sys.executable,str(OUT/'read_history.py')],input=json.dumps(request),text=True,capture_output=True,check=True,timeout=60)
    exported=json.loads(result.stdout);chosen={int(n):r for n,r in exported['chosen'].items()}
    scan=copy.copy(d['scan']);scan.receipt=dict(scan.receipt)
    oldpath=scan.previous_tle_path;receipt=read(oldpath.parent/'previous_receipt.json');text=oldpath.read_text().rstrip()+'\n'
    for n,r in chosen.items():
        text+='\n'.join(r['lines'])+'\n';receipt['sources'][str(n)]={k:v for k,v in r.items() if k!='lines'}
    path=out/'history'/'previous.tle';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    write(path.parent/'previous_receipt.json',receipt);scan.previous_tle_path=path;scan.receipt['previous_tle_sha256']=sha(path)
    for attr in ('previous_shape_cache','diagnostic_phase_width_cache','causal_uncertainty_modes','reference_motion_derivatives','mean_motion_derivatives'):
        if hasattr(scan,attr):delattr(scan,attr)
    return dict(d,scan=scan),dict(available=chosen,missing=sorted(new_ids-set(chosen)),snapshot_count=exported['snapshot_count'],old_previous_sha256=sha(oldpath),extended_previous_sha256=sha(path),read_only_privileged_export=True)

def apply_hypothesis(d,z,case,h,out):
    # Existing adapter consumes a ledger through PRIOR. Redirect only its ledger
    # lookup to this run's frozen causal catalogue, not its numerical code.
    saved=ex.PRIOR;ex.PRIOR=OUT/'ledgers'
    try:dd=ex.remap(d,z,case,h)
    finally:ex.PRIOR=saved
    # Use the production signed-history mean for all newly labeled families.
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    base=dd['problems']['fitted_c'][0];_,receipts=phase_widths(dd['scan'],base.labels)
    forecast=forecast_phase_mean(receipts,dd['model']['shrinkage']);oldmeans=dict(zip(d['problems']['fitted_c'][0].labels,d['means']))
    dd['means']=np.array([oldmeans.get(j,forecast[k]) for k,j in enumerate(base.labels)])
    for a in ARMS:
        p,x=dd['problems'][a];q,_=build(dd,z,a,p.reference);dd['problems'][a]=(q,x)
    return dd,receipts

def run(case):
    out=OUT/case;out.mkdir(parents=True,exist_ok=True);z=read(INPUT/(case+'.json'));d=reconstruct(z)
    ranking,targets=rank_families(d,z);write(out/'trigger.json',dict(ranking=ranking,selected=targets,replay=d['replay_checks']))
    ledger=causal_records(case,z);write(OUT/'ledgers'/case/'tle-ledger.json',dict(causal=ledger))
    nums,bank,failed=bank_for(ledger,z['scan_receipt']['origin_utc_ns']);records=[]
    for n in targets:
        folder=out/str(n);folder.mkdir(exist_ok=True)
        screened=read(folder/'screen.json') if (folder/'screen.json').exists() else screen(d,z,n,nums,bank,folder)
        write(folder/'screen.json',screened)
        for h in screened.get('proposals',[]):
            rows=[]
            try:
                enriched,history=extend_history(d,z,case,set(h['mapping'].values()),folder/h['name'])
                dd,receipts=apply_hypothesis(enriched,z,case,h,folder)
                starts={'published':d['problems']['fitted_c'][1],'family_omitted':np.array(screened['cavity']['fitted_c']['x'])}
                for a in ARMS:
                    for label,start in starts.items():
                        try:
                            r=previous.fit(dd,z,a,start,True,rounds=15)
                            r['unexpected_reassigned_ids']=[o for o in r['reassigned_ids'] if z['baseline_owners'][a][o] not in h['allowed_families']]
                            r['qualified'] &= not r['unexpected_reassigned_ids']
                            r.update(arm=a,start=label,status='complete');r.pop('proposed_owners');rows.append(r)
                        except Exception as exc:rows.append(dict(arm=a,start=label,status='incomplete',qualified=False,reason=repr(exc)))
                record=dict(target=n,hypothesis=h,history=history,phase_history=receipts,rows=rows)
            except Exception as exc:record=dict(target=n,hypothesis=h,rows=rows,error=repr(exc))
            records.append(record);write(folder/(h['name']+'.json'),record)
            print(case,h['name'],[(r['arm'],r.get('error_m'),r['qualified']) for r in rows],flush=True)
    candidates=[]
    for rec in records:
        h=rec['hypothesis'];pair={a:min((r for r in rec['rows'] if r['arm']==a and r['qualified']),key=lambda r:r['objective'],default=None) for a in ARMS}
        prediction=all(h['predictive'][a]['pass_check'] for a in ARMS) and 'prediction_limit' not in h
        if not all(pair.values()):continue
        gains={a:objective(*[d['problems'][a][0],d,d['problems'][a][1]])-pair[a]['objective']-h['penalty'] for a in ARMS}
        rec['paired_gain']=gains;rec['prediction_pass']=prediction
        if prediction and all(g>0 for g in gains.values()):candidates.append((sum(gains.values()),rec,pair))
    selected=max(candidates,key=lambda q:q[0]) if candidates else None
    result=dict(case=case,triggered=targets,catalogue_size=len(nums),propagation_failures=failed,selected=selected[1]['hypothesis']['name'] if selected else None,
        baseline={a:dict(x=x,error_m=previous.error(x),objective=objective(p,d,x),associated=len(z['baseline_owners'][a])) for a,(p,x) in d['problems'].items()},
        final={a:dict(x=selected[2][a]['x'],error_m=selected[2][a]['error_m'],objective=selected[2][a]['objective'],associated=len(z['baseline_owners'][a])) if selected else dict(x=x,error_m=previous.error(x),objective=objective(p,d,x),associated=len(z['baseline_owners'][a])) for a,(p,x) in d['problems'].items()},
        records=records,production_changed=False)
    write(out/'result.json',result);print(case,'SELECTED',result['selected'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case');args=parser.parse_args()
    freeze() if args.case=='freeze' else run(args.case)
