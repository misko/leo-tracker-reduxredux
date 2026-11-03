"""Bounded native-track investigation; never changes inference or ownership."""
import argparse
import csv
import gzip
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from sgp4.api import Satrec
from diagnose_all_large_tracks import context
from analyze_dsx01_fixed_site import ecef_states
from investigate_ds23_0268_remaining_tracks import corrected_observation, family_frequency
from prototype_dsx01_continuous_position import latlon
from leo.sky.propagation import ElementSetCatalogue
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.robust_polynomial_order import polynomial_orders

PRODUCTION = Path('/srv/bulk/leo-dev/fast-algo02-production-v1')
INVENTORY = PRODUCTION / 'reports/2026_10_31_algo05_promotion/residuals'
MODELS = {'phase_offset': (0., 300.), 'phase_small_rate': (.5, 300.),
          'phase_wider_rate': (2., 1000.), 'affine_control': (30., 1e6)}
PHASES = np.arange(-15., 15.01, 1.)
ARMS = ('c0', 'fitted_c')


def read(p):
    return json.loads(Path(p).read_text())


def encode(x):
    if isinstance(x, np.ndarray): return x.tolist()
    if isinstance(x, np.generic): return x.item()
    raise TypeError(type(x).__name__)


def write(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, default=encode, allow_nan=False, indent=2) + '\n')


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def subbank(bank, j):
    return dict(time_s=bank['time_s'], position_km=bank['position_km'][[j]], velocity_km_s=bank['velocity_km_s'][[j]])


def scalar_noise(res, t):
    r = batch_noise_screen(np.asarray(res)[None], t)
    return {k: v[0].item() for k, v in r.items()}


def random_groups(times, seed):
    groups = np.floor(np.asarray(times) / 12).astype(int)
    unique = np.unique(groups); rng = np.random.default_rng(seed)
    selected = rng.choice(unique, max(1, round(len(unique) / 3)), replace=False)
    held = np.isin(groups, selected)
    train = ~held
    for g in selected: train &= (times < g * 12 - 2) | (times >= (g + 1) * 12 + 2)
    return train, held, selected


def polynomial_audit(t, y):
    rows = polynomial_orders(t, y, noise_hz=150., maximum_degree=4)
    x = (t - t.mean()) / np.ptp(t)
    constant = np.full(len(t), y.mean())
    ordinary = []
    for degree in range(5):
        design = np.polynomial.polynomial.polyvander(x, degree)
        pred = design @ np.linalg.lstsq(design, y, rcond=None)[0]
        ordinary.append(dict(degree=degree, rms_hz=float(np.sqrt(np.mean((y-pred)**2))),
                             penalty=(degree+1)*np.log(len(t)), noise=scalar_noise(y-pred,t)))
    best = rows[0]; degree = best['degree']; design = np.polynomial.polynomial.polyvander(x, degree)
    full = design @ np.linalg.lstsq(design,y,rcond=None)[0]
    endpoint = []
    for omitted in (0,len(t)-1):
        keep = np.arange(len(t)) != omitted
        pred = design @ np.linalg.lstsq(design[keep], y[keep],rcond=None)[0]
        endpoint.append(dict(index=omitted, held_error_hz=float(y[omitted]-pred[omitted]),
                             max_curve_change_hz=float(np.max(abs(pred-full)))))
    return dict(robust_orders=rows, ordinary_orders=ordinary, endpoint_sensitivity=endpoint,
                active_curvature_rms_hz=float(np.sqrt(np.mean((full-np.polynomial.polynomial.polyvander(x,1) @ np.linalg.lstsq(np.polynomial.polynomial.polyvander(x,1),full,rcond=None)[0])**2))),
                constant_rms_hz=float(np.std(y)), effective_sample_caveat='order score assumes independent 150 Hz noise; predictive groups are reported separately')


def propagate_post(export, times, origin):
    records = list(export['elements'].values())
    if not records: return None, [], []
    sats = tuple(Satrec.twoline2rv(*r['lines']) for r in records)
    cat = ElementSetCatalogue(tuple(str(r['norad']) for r in records), tuple(r['norad'] for r in records), sats)
    pos, vel, usable = ecef_states(cat, origin, times)
    good = np.all(usable, axis=-1) if usable.ndim == 2 else usable
    return dict(time_s=times, position_km=pos[good], velocity_km_s=vel[good]), np.array([r['norad'] for r in records])[good], [r['norad'] for r,g in zip(records,good) if not g]


def published(case):
    selected = next(r['selected'] for r in read(INVENTORY/'selections.json') if r['case']==case)
    if case.startswith('DS26'):
        base = read(Path('/srv/bulk/leo/research/ds26-confident-recovery-20261031/baselines')/(case+'.json'))
        owners, arms = base['owners'],base['arms']
    else:
        from importlib.util import spec_from_file_location, module_from_spec
        spec=spec_from_file_location('native_rank',PRODUCTION/'reports/2026_10_31_algo05_promotion/reproduction/rank_native_residuals.py')
        mod=module_from_spec(spec);spec.loader.exec_module(mod)
        entry=next(r for r in read('/srv/bulk/leo/research/ds27-algo04-20261031/analysis-index.json')['cases'] if r['case']==case)
        term=read(entry['terminal_path']);owners={a:mod.published_owners(term,a) for a in ARMS}
        proof=term['candidate'] if term['decision']=='ALGO04_additive' else term['incumbent']
        arms=proof['selected']['arms'] if proof.get('selected') else proof['baseline']['arms']
    if selected:
        arms=read(Path(selected['path'])/'target_0.json')['arms']
        owners={a:arms[a]['proposed_owners'] for a in ARMS}
    return owners,arms


def coarse(bank,numbers,t,y,position,q):
    pick=np.unique(np.linspace(0,len(t)-1,min(16,len(t))).astype(int));tt=t[pick]
    best={m:np.full(len(numbers),np.inf) for m in MODELS}
    phase={m:np.zeros(len(numbers)) for m in MODELS}
    for phi in PHASES:
        f,e=phase_frequency_grid(bank,tt,*latlon(position),phase_seconds=phi)
        for m,(rate,bias) in MODELS.items():
            cost=profile_rate(y[pick],q*f,tt,rate_sigma_hz_s=rate,bias_sigma_hz=bias)['cost']+(phi/5.)**2
            cost=np.where(e.min(axis=1)>=0,cost,np.inf)
            update=cost<best[m];best[m][update]=cost[update];phase[m][update]=phi
    return {m:[dict(norad=int(numbers[j]),phase=float(phase[m][j]),cost=float(best[m][j]))
               for j in np.argsort(best[m])[:5] if np.isfinite(best[m][j])] for m in MODELS}


def exact(bank,j,norad,t,y,position,q,model,train=None,phase_fixed=None,phase_limit=15.):
    rate,bias=MODELS[model];small=subbank(bank,j);mask=np.ones(len(t),bool) if train is None else train
    def ev(phi):
        f,e=phase_frequency_grid(small,t,*latlon(position),phase_seconds=float(phi));f=q*f[0]
        v=profile_rate(y[mask],f[mask],t[mask],rate_sigma_hz_s=rate,bias_sigma_hz=bias)
        score=float(v['cost'][0]+(phi/5.)**2)
        if e[0,mask].min()<0:score+=1e12
        return score,v,f,e[0]
    if phase_fixed is None:
        phases=np.arange(-phase_limit,phase_limit+.01,1.)
        values=[ev(phi)[0] for phi in phases];k=int(np.argmin(values));seed=phases[k]
        fit=minimize_scalar(lambda phi:ev(phi)[0],bounds=(max(-phase_limit,seed-1),min(phase_limit,seed+1)),method='bounded',options={'xatol':.002,'maxiter':24})
        phi=float(fit.x)
        if values[k]<fit.fun:phi=float(seed)
    else: phi=float(np.clip(phase_fixed,-phase_limit,phase_limit))
    cost,v,f,e=ev(phi);offset=float(v['bias_hz'][0]);slope=float(v['rate_hz_s'][0]);alias=int(v['alias'][0])
    correction=offset+slope*(t-t[mask].mean());res=y+alias*PERIOD-f-correction
    noise=scalar_noise(res,t)
    return dict(norad=int(norad),model=model,phase_s=phi,offset_hz=offset,rate_hz_s=slope,alias=alias,cost=cost,
                rms_hz=float(np.sqrt(np.mean(res**2))),minimum_elevation_deg=float(e.min()),
                passes_screen=bool(noise['noise_screen_pass'] and np.sqrt(np.mean(res**2))<=450 and abs(offset)<=3000 and e.min()>=0),
                noise=noise,orbit_hz=f,correction_hz=correction,residual_hz=res,
                phase_at_bound=abs(phi)>phase_limit-.02,parameter_prior_pulls=dict(phase=phi/5,offset=offset/bias,rate=slope/rate if rate else 0))


def family_transfer(d,p,x,owners,bank,numbers,norad,target,t,y,model):
    """Fit phase/shared frequency rate on independently owned curved tracks only."""
    supported=[]
    for i,sl,row in zip(p.members,p.slices,p.rows):
        if i==target or row['candidate_norad']!=norad:continue
        tr=d['scan'].tracks[i];keep=np.array([owners.get(oid)==norad for oid in tr['observation_ids']]) & p.keep[sl]
        if keep.sum()>=8: supported.append((i,keep))
    if not supported:return dict(status='no_independent_active_curved_family_support')
    j=int(np.flatnonzero(numbers==norad)[0]);small=subbank(bank,j)
    ts=np.concatenate([d['scan'].tracks[i]['times'][keep] for i,keep in supported]);center=float(ts.mean())
    ys=np.concatenate([corrected_observation(p,x,i)[keep]/(d['scan'].tracks[i]['rf_hz']/11.5e9) for i,keep in supported])
    lengths=[int(keep.sum()) for _,keep in supported];g=np.repeat(np.arange(len(lengths)),lengths)
    alias_periods=[PERIOD/(d['scan'].tracks[i]['rf_hz']/11.5e9) for i,_ in supported]
    # Independent source biases absorb unknown carrier constants, while rate is shared.
    design=np.eye(len(lengths))[g]*300.; rate=.5 if model=='phase_small_rate' else 0.
    if rate:design=np.column_stack((design,rate*(ts-center)))
    gram=np.eye(design.shape[1])+design.T@design/150.**2
    def ev(phi):
        f,e=phase_frequency_grid(small,ts,*latlon(x),phase_seconds=float(phi));raw=ys-f[0]
        for z in range(len(lengths)):
            period=alias_periods[z];raw[g==z]+=round(-raw[g==z].mean()/period)*period
        coef=np.linalg.solve(gram,design.T@raw/150.**2);res=raw-design@coef
        cost=float(np.sum((res/150.)**2)+coef@coef+(phi/5)**2)
        if e.min()<0:cost+=1e12
        return cost,coef
    grid=[ev(phi)[0] for phi in PHASES];phi0=PHASES[np.argmin(grid)]
    fit=minimize_scalar(lambda z:ev(z)[0],bounds=(max(-15,phi0-1),min(15,phi0+1)),method='bounded')
    phi=float(fit.x);_,coef=ev(phi);slope=float(coef[-1]*rate) if rate else 0.
    f,e=phase_frequency_grid(small,t,*latlon(x),phase_seconds=phi);q=d['scan'].tracks[target]['rf_hz']/11.5e9
    prediction=q*(f[0]+slope*(t-center));v=profile_rate(y,prediction,t,bias_sigma_hz=300.)
    res=v['residual_hz'][0]
    return dict(status='independent_family_transfer',support_tracks=[d['scan'].tracks[i]['key'] for i,_ in supported],support_points=len(ts),
                phase_s=phi,shared_rate_hz_s_at_11_5GHz=slope,target_rms_hz=float(v['rms_hz'][0]),
                target_bias_hz=float(v['bias_hz'][0]),target_noise=scalar_noise(res,t),target_residual_hz=res,
                note='target only profiles a 300 Hz bias; target never fits shared phase/rate; receiver calibration frozen')


def run_case(args):
    started=time.monotonic();rows=[r for r in read(args.output/'targets.json') if r['case']==args.case]
    inv=read(rows[0]['inventory_path']);d=context(inv);scan=d['scan'];owners,public=published(args.case)
    native=Path(inv['job']['root'])/inv['job']['case'];obs=read(native/'observations.json')
    packet=json.loads(gzip.open(INVENTORY/args.case[:4]/'plot-inputs.json.gz','rt').read())['cases'][args.case]
    assert set(owners['fitted_c'])==set(packet['associated_ids'])
    # Recondition inherited calibration at the actually published endpoint; no target admitted.
    positions={a:np.asarray(public[a]['endpoint_east_north_km']) for a in ARMS}
    post_export=read(args.output/'post_tles.json')['scans'][args.case]
    post,numbers,unusable=propagate_post(post_export,scan.sky['time_s'],scan.receipt['origin_utc_ns'])
    banks={'causal':(scan.sky,np.asarray(scan.norads))}
    if post is not None:banks['later']=(post,numbers)
    out=args.output/'cases'/args.case;out.mkdir(parents=True,exist_ok=True)
    ledger=[]
    for n,r in scan.elements.items():
        prov=r['provenance'];assert prov['collected_utc_ns']<=scan.receipt['cutoff_utc_ns'] and prov['element_epoch_utc_ns']<=scan.receipt['cutoff_utc_ns']
        ledger.append(dict(prov, norad=int(n),regime='causal',element_hash=hashlib.sha256(('\n'.join(r['lines'])+'\n').encode()).hexdigest()))
    ledger += [dict(regime='later',**{k:v for k,v in r.items() if k!='lines'}) for r in post_export['elements'].values()]
    write(out/'tle_inventory.json',ledger)
    results=[]
    for row in rows:
        track=scan.tracks[row['track_index']];indices=np.asarray(row['source_local_indices']);t=track['times'][indices];values=track['values'][indices];q=track['rf_hz']/11.5e9
        assert len(t)==row['points'] and not set(row['observation_ids']) & set(owners['fitted_c'])
        observed={a:corrected_observation(d['problems'][a][0],positions[a],row['track_index'])[indices] for a in ARMS}
        poly=polynomial_audit(t,values)
        offers={reg:{a:coarse(bank,nums,t,observed[a],positions[a],q) for a in ARMS} for reg,(bank,nums) in banks.items()}
        # Same finalist universe across model levels, both c arms, and paired TLE banks.
        finalists=sorted({offer['norad'] for arms in offers.values() for mods in arms.values() for v in mods.values() for offer in v})
        old=next((r for r in read(INVENTORY/'diagnostics/analysis.json') if r['case']==row['case'] and r['key']==row['key']),None)
        if old and old.get('identity') and old['identity'].get('norad'):finalists=sorted(set(finalists)|{old['identity']['norad']})
        fits=[];comparisons=[]
        for reg,(bank,nums) in banks.items():
            lookup={int(n):j for j,n in enumerate(nums)}
            for a in ARMS:
                p,_=d['problems'][a];x=positions[a];y=observed[a]
                for norad in finalists:
                    if norad not in lookup:continue
                    j=lookup[norad]
                    for model in MODELS:
                        r=exact(bank,j,norad,t,y,x,q,model);r.update(regime=reg,arm=a);fits.append(r)
            print(args.case,row['key'],reg,'finalists',len(finalists),flush=True)
        validation=[];transfers=[];swaps=[]
        for reg,(bank,nums) in banks.items():
            lookup={int(n):j for j,n in enumerate(nums)}
            for model in ('phase_offset','phase_small_rate'):
                top=sorted({r['norad'] for a in ARMS for r in sorted([r for r in fits if r['regime']==reg and r['arm']==a and r['model']==model],key=lambda r:r['cost'])[:3]})
                for a in ARMS:
                    for n in top:
                        for seed in (20261031,94721,4081):
                            train,held,groups=random_groups(t,seed)
                            if train.sum()<8 or held.sum()<4:continue
                            r=exact(bank,lookup[n],n,t,observed[a],positions[a],q,model,train=train)
                            validation.append(dict(regime=reg,arm=a,model=model,norad=n,seed=seed,held_groups=groups,train_indices=np.flatnonzero(train),held_indices=np.flatnonzero(held),held_rms_hz=float(np.sqrt(np.mean(r['residual_hz'][held]**2))),phase_s=r['phase_s'],offset_hz=r['offset_hz'],rate_hz_s=r['rate_hz_s']))
                    winner=min((r for r in fits if r['regime']==reg and r['arm']==a and r['model']==model),key=lambda r:r['cost'])
                    tr=family_transfer(d,d['problems'][a][0],positions[a],owners[a],bank,nums,winner['norad'],row['track_index'],t,observed[a],model)
                    transfers.append(dict(regime=reg,arm=a,model=model,norad=winner['norad'],**tr))
        if 'later' in banks:
            bank,nums=banks['later'];lookup={int(n):j for j,n in enumerate(nums)}
            for a in ARMS:
                for model in MODELS:
                    winner=min((r for r in fits if r['regime']=='causal' and r['arm']==a and r['model']==model),key=lambda r:r['cost'])
                    n=winner['norad']
                    if n not in lookup:swaps.append(dict(arm=a,model=model,norad=n,status='later_TLE_missing'));continue
                    f,e=phase_frequency_grid(subbank(bank,lookup[n]),t,*latlon(positions[a]),phase_seconds=winner['phase_s'])
                    res=observed[a]+winner['alias']*PERIOD-q*f[0]-winner['correction_hz']
                    refit=next(r for r in fits if r['regime']=='later' and r['arm']==a and r['model']==model and r['norad']==n)
                    swaps.append(dict(arm=a,model=model,norad=n,status='paired',causal_rms_hz=winner['rms_hz'],frozen_later_rms_hz=float(np.sqrt(np.mean(res**2))),refit_later_rms_hz=refit['rms_hz']))
        baseline=[]
        best=sorted([r for r in fits if r['regime']=='causal' and r['arm']=='fitted_c' and r['model']=='phase_offset'],key=lambda r:r['cost'])[0]
        for a in ARMS:
            p,_=d['problems'][a];x=positions[a];j=int(np.flatnonzero(scan.norads==best['norad'])[0])
            try:
                f,e=family_frequency(p,x,j,times=t);v=profile_rate(observed[a],q*f,t,bias_sigma_hz=300.)
                baseline.append(dict(arm=a,norad=best['norad'],rms_hz=float(v['rms_hz'][0]),noise=scalar_noise(v['residual_hz'][0],t),prediction_hz=q*f,residual_hz=v['residual_hz'][0],phase_s=float(p.state(x)['phases'][j])))
            except ValueError as exc: baseline.append(dict(arm=a,status='unavailable',reason=str(exc)))
        attribution=[]
        for i,sl,pr in zip(d['problems']['fitted_c'][0].members,d['problems']['fitted_c'][0].slices,d['problems']['fitted_c'][0].rows):
            p,_=d['problems']['fitted_c'];tr=scan.tracks[i]
            if not p.keep[sl].any() or i==row['track_index']:continue
            if tr['receiver']!=track['receiver'] and pr['candidate_norad']!=best['norad']:continue
            tt=tr['times'];mask=p.keep[sl]& (tt>=t.min()-10)&(tt<=t.max()+10)
            if mask.sum()<8:continue
            f,e=family_frequency(p,positions['fitted_c'],pr['candidate_index'],times=tt)
            v=profile_rate(corrected_observation(p,positions['fitted_c'],i)[mask],tr['rf_hz']/11.5e9*f[mask],tt[mask],rate_sigma_hz_s=30.,bias_sigma_hz=1e6)
            attribution.append(dict(track=tr['key'],norad=pr['candidate_norad'],receiver=tr['receiver'],channel=tr['channel'],points=int(mask.sum()),rate_hz_s=float(v['rate_hz_s'][0]),rms_hz=float(v['rms_hz'][0]),same_family=pr['candidate_norad']==best['norad']))
        item=dict(source=row,times_s=t,values_hz=values,corrected_hz=observed,polynomial=poly,offers=offers,finalists=finalists,fits=fits,
                  grouped_validation=validation,family_transfer=transfers,paired_TLE_swaps=swaps,baseline_shared_model=baseline,
                  receiver_family_attribution=attribution,previous_evidence=old,
                  validation_caveat='random whole 12s groups, 2s guard; conditional on full-data finalist selection and inherited graph/calibration; not an unbiased identity probability')
        write(out/(row['fragment_id']+'.json'),item);results.append(dict(fragment_id=row['fragment_id'],key=row['key']))
    write(out/'receipt.json',dict(case=args.case,results=results,baseline_objective_replay=d.get('replay'),positions=positions,
          calibration_policy='inherited sealed baseline normal equations reconditioned at published ALGO05 endpoints; target excluded; no accepted owners modified',
          original_baseline_positions={a:d['problems'][a][1] for a in ARMS},catalogue_counts={k:len(v[1]) for k,v in banks.items()},
          post_propagation_failures=unusable,scan_receipt=scan.receipt,
          hashes={str(p):digest(p) for p in [Path(rows[0]['inventory_path']),native/'tracks.json',native/'observations.json',native/'bank.npz',args.output/'post_tles.json']},seconds=time.monotonic()-started))
    print(args.case,'DONE',round(time.monotonic()-started,1),'seconds',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--case',required=True)
    run_case(parser.parse_args())
