"""Matched fixed-bank, all-top-window profile likelihood near the known roof.

Same finite-set likelihood and timing priors as the earlier position test.
Current fitted-c receiver baseline is frozen identically in both RF arms;
additional RX constants/slopes, common RF coefficient and satellite timing
are profiled. This is conditional in-sample sensitivity, not blind localization.
"""
import argparse,copy,json,time,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from concurrent.futures import ProcessPoolExecutor,ThreadPoolExecutor
import multiprocessing
from replay import ROOT,NAMESPACE,digest
sys.path[:0]=[str(ROOT.parent/name) for name in ('2026_10_02_ds13_timing_em','2026_10_02_multiscan_localization','2026_10_02_localization_benchmark','2026_10_03_ds13_multitarget')]

OUT=NAMESPACE/'position-top-2km'
SEED=20261004

def save(path,value):
    def convert(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        raise TypeError(type(x))
    path.write_text(json.dumps(value,default=convert,indent=2,allow_nan=False))

def point_design(seed=SEED):
    rng=np.random.default_rng(seed)
    pts=[dict(label='roof',east_m=0.,north_m=0.,kind='roof')]
    for h in (50.,100.):
        for e,n in ((h,0.),(-h,0.),(0.,h),(0.,-h)):
            pts.append(dict(label=f'cardinal-{e}-{n}',east_m=e,north_m=n,kind='derivative'))
    for band,(lo,hi) in enumerate(((0.,500.),(500.,1000.),(1000.,1500.),(1500.,2000.))):
        for sector in range(12):
            angle=rng.uniform(sector*np.pi/6,(sector+1)*np.pi/6)
            radius=np.sqrt(rng.uniform(lo*lo,hi*hi))
            pts.append(dict(label=f'random-{band}-{sector}',east_m=radius*np.sin(angle),north_m=radius*np.cos(angle),kind='random'))
    for j in range(16):
        angle=j*2*np.pi/16
        pts.append(dict(label=f'boundary-{j}',east_m=2000*np.sin(angle),north_m=2000*np.cos(angle),kind='boundary'))
    return pts

def prepare(label):
    from gap_allfold_summary import location
    from rf_calibration_diagnostic import rf_features
    from joint_inputs import _coordinates
    if label=='A':
        from top_one_scan_A import TopOneCalibration
        cal=TopOneCalibration();folder=NAMESPACE/'full-scan-A-refinement/top-one'
    else:
        from position_top_2km_inputs import calibration
        cal=calibration()();folder=OUT/'B-top'
    results={a:json.loads((folder/f'{a}.json').read_text()) for a in ('fitted-c','zero-c')}
    chosen={a:{m['catalog_number']:m for m in r['final']['selected']} for a,r in results.items()}
    numbers=sorted(set(chosen['fitted-c'])|set(chosen['zero-c']))
    ids=np.array([int(np.flatnonzero(cal.d.numbers==n)[0]) for n in numbers]);d=cal.d
    fixed=[];fold_coeff=[];coefficients=[]
    for fold,(part,models) in enumerate(cal.parts):
        sp=location(fold,'corrected')/'training-union'/f'fold-{fold}'/f'{label}.json'
        receipt=json.loads(sp.read_text());coef=float(receipt['arms']['fitted-c']['coefficient'][0])
        full_rf=cal.data.rf[np.asarray(receipt['original_test_rows'],int)]
        center=float(np.mean(np.unique(full_rf)));feature=(part.rf-center)/1e9
        p,_,correction=models['fitted-c']
        q=correction-feature*coef+p[2+2*part.receiver]+p[3+2*part.receiver]*(part.times-150.)
        fixed.extend(q);fold_coeff.extend(feature*coef);coefficients.append(coef)
    assert np.array_equal(np.concatenate([part.original_rows for part,_ in cal.parts]),d.original_rows)
    fixed=np.asarray(fixed);full_rf_correction=np.asarray(fold_coeff)
    known=cal.parts[0][1]['fitted-c'][0][:2]
    initial=np.zeros(6+len(numbers));initial[:2]=known
    for j,n in enumerate(numbers):initial[6+j]=chosen['fitted-c'].get(n,chosen['zero-c'].get(n))['offset_s']
    compact=copy.copy(d);compact.numbers=np.asarray(numbers);compact.position=d.position[ids];compact.velocity=d.velocity[ids]
    compact.measured=d.measured-fixed;compact.initial=initial
    # Reconstruct the original model before introducing the single refitted RF coefficient.
    from prediction_plan import SharedPredictionPlan
    p,_,_=SharedPredictionPlan(compact,np.arange(len(numbers))).predict(initial)
    frozen=np.column_stack([cal.predict('fitted-c',np.array([sid]),initial[6+j])[0][:,0] for j,sid in enumerate(ids)])
    difference=float(np.max(abs(p.reshape(len(d.times),-1)+fixed[:,None]+full_rf_correction[:,None]-frozen)))
    assert difference<1e-5,difference
    fields=('numbers','position','velocity','nodes','times','measured','rf','receiver','channel','group','margin','original_rows','initial')
    OUT.mkdir(exist_ok=True)
    np.savez_compressed(OUT/f'{label}-profile-input.npz',**{k:getattr(compact,k) for k in fields},fixed_receiver_hz=fixed,raw_refined_hz=d.measured)
    sources=dict(cal.sources);sources.update({str(folder/f'{a}.json'):digest(folder/f'{a}.json') for a in results})
    save(OUT/f'{label}-profile-input.json',dict(scan=label,rows=len(d.times),satellites=numbers,
        selected_by_arm={a:sorted(chosen[a]) for a in chosen},roof_position_km=known,roof_lat_lon=_coordinates(known),
        seed_coefficient_hz_per_ghz=float(np.median(coefficients)),model_reconstruction_max_error_hz=difference,
        sources=sources,coverage={a:r['final']['coverage'] for a,r in results.items()},
        sigma_hz=200.,clutter_rate=2.,detection_probability=.8/len(numbers),
        scope=__doc__,baseline='Identical fixed fitted-c RX offsets/slopes and spline in both arms; RF contribution removed before profiling.',
        profile='Additional RX offsets/slopes and absolute RF coefficient refit; timing common sigma=10 s, relative sigma=1 s, zero-centered. No curvature filtering.'))
    print('PREPARED',label,len(d.times),len(numbers),'reconstruction',difference,flush=True)

class Engine:
    def __init__(self,label,arm):
        from rf_calibration_diagnostic import CalibrationObjective
        from position_profile_grid import geodesic_position
        self.label=label;self.arm=arm;self.meta=json.loads((OUT/f'{label}-profile-input.json').read_text())
        with np.load(OUT/f'{label}-profile-input.npz') as z:self.data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
        self.obj=CalibrationObjective(self.data,self.data.initial,np.arange(len(self.data.numbers)),False,8.)
        self.obj.base.minimum_shift_s=max(self.obj.base.minimum_shift_s,-20.)
        self.obj.base.maximum_shift_s=min(self.obj.base.maximum_shift_s,20.)
        if arm=='zero-c':self.obj.bounds[-1]=(0.,0.)
        self.initial=self.obj.initial.copy();self.initial[-1]=0 if arm=='zero-c' else self.meta['seed_coefficient_hz_per_ghz']
        self.lat,self.lon=self.meta['roof_lat_lon'];self.cache={};self.calls=[]
        self.folder=OUT/'profiles'/f'{label}-{arm}';self.folder.mkdir(parents=True,exist_ok=True)
        for path in sorted(self.folder.glob('fit-*.json')):
            r=json.loads(path.read_text());self.cache[(round(r['east_m'],5),round(r['north_m'],5))]=r;self.calls.append(r)

    def coordinate(self,point):
        from position_profile_grid import geodesic_position
        e,n=np.asarray(point)*1000
        return geodesic_position(self.lat,self.lon,np.degrees(np.arctan2(e,n)),np.hypot(e,n))

    def position_gradient(self,point,gradient):
        step=.001
        jac=np.column_stack([(self.coordinate(np.array(point)+np.eye(2)[i]*step)-self.coordinate(np.array(point)-np.eye(2)[i]*step))/(2*step) for i in range(2)])
        return jac.T@gradient

    def fit(self,point,label='optimization',force_start=None):
        from truth_start_diagnostic import optimize,projected_gradient
        p=np.asarray(point,float);key=tuple(np.round(p*1000,5))
        if key in self.cache and force_start is None and self.cache[key]['success']:return self.cache[key]
        if force_start is None:
            nearby=min(self.cache.values(),key=lambda r:np.hypot(r['east_m']-key[0],r['north_m']-key[1])) if self.cache else None
            current=np.asarray(nearby['vector']).copy() if nearby else self.initial.copy()
        else:current=np.asarray(force_start).copy()
        current[:2]=self.coordinate(p);bounds=list(self.obj.bounds);bounds[:2]=[(v,v) for v in current[:2]]
        attempts=[];started=time.monotonic()
        for _ in range(3):
            fitted=optimize(self.obj,current,bounds,budget_s=8.);current=np.asarray(fitted['vector'])
            attempts.append({k:fitted[k] for k in ('objective','success','status','projected_gradient_inf_norm','elapsed_s')})
            if fitted['success']:break
        self.obj.base.deadline=float('inf');value,gradient=self.obj.evaluate(current)
        _,_,j=self.obj.base.predict(current[:self.obj.size],with_jacobian=True)
        ll=self.obj.likelihood.last_result;pred,vis,_=self.obj.base.plan.predict(self.obj.base.state(current[:self.obj.size])['parameters'])
        pred=pred.reshape(len(self.data.times),-1)+(self.obj.features@current[self.obj.size:])[:,None]
        from finite_set_likelihood import circular_residual
        residual=circular_residual(self.data.measured[:,None],pred,1/4.4e-6)
        best=np.min(np.where(vis.reshape(residual.shape),abs(residual),np.inf),axis=1)
        prior=float(self.obj.base.penalty(current[:self.obj.size])[0]);data_nll=-float(ll['total_log_likelihood'])
        assert abs(value-data_nll-prior)<1e-7
        r=dict(scan=self.label,arm=self.arm,label=label,east_m=p[0]*1000,north_m=p[1]*1000,
            objective=float(value),data_nll=data_nll,prior_nll=prior,vector=current,
            gradient_per_km=self.position_gradient(p,gradient[:2]),nuisance_gradient=float(fitted['projected_gradient_inf_norm']),
            success=bool(fitted['success']),attempts=attempts,elapsed_s=time.monotonic()-started,
            inside600=int(sum(best<=600)),nearest_rms_inside600_hz=float(np.sqrt(np.mean(best[best<=600]**2))),
            c_hz_per_ghz=float(current[-1]),rx_adjustment=current[2:6],
            total_timing_s=self.obj.base.state(current[:self.obj.size])['total_shifts_s'])
        index=len(self.calls);save(self.folder/f'fit-{index:04d}.json',r);self.calls.append(r)
        if key not in self.cache or r['objective']<self.cache[key]['objective'] or (r['success'] and not self.cache[key]['success'] and r['objective']<=self.cache[key]['objective']+1e-5):self.cache[key]=r
        print(self.label,self.arm,label,np.round(p*1000,1),'score',round(value,4),'gradient',round(r['nuisance_gradient'],5),'ok',r['success'],'s',round(r['elapsed_s'],1),flush=True)
        return self.cache[key]

def smoke(label):
    for arm in ('fitted-c','zero-c'):
        engine=Engine(label,arm);roof=engine.fit([0,0],'roof')
        engine.fit([.1,0],'smoke-east')
        assert roof['success'],roof['attempts']

def probe_worker(task):
    label,arm,design=task;engine=Engine(label,arm)
    for point in design:
        fit=engine.fit(np.array([point['east_m'],point['north_m']])/1000,point['label'])
        if not fit['success']:raise RuntimeError(f'Unconverged {label} {arm} {point}')
    return label,arm,len(engine.calls)

def run():
    from scipy.optimize import minimize
    started=time.monotonic()
    design=point_design();save(OUT/'point-design.json',dict(seed=SEED,points=design))
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('fork')) as pool:
        for result in pool.map(probe_worker,[(s,a,design) for s in ('A','B') for a in ('fitted-c','zero-c')]):print('PROBES COMPLETE',result,flush=True)
    engines={(s,a):Engine(s,a) for s in ('A','B') for a in ('fitted-c','zero-c')}
    profiles=ThreadPoolExecutor(max_workers=2)
    minima={}
    def joint(arm,x):
        r=list(profiles.map(lambda s:engines[s,arm].fit(x),('A','B')))
        if not all(t['success'] for t in r):raise RuntimeError('Unconverged nuisance profile')
        return sum(t['objective'] for t in r),np.sum([t['gradient_per_km'] for t in r],axis=0)
    for arm in ('fitted-c','zero-c'):
        ranked=sorted(design,key=lambda p:joint(arm,np.array([p['east_m'],p['north_m']])/1000)[0])
        starts=[np.zeros(2)]
        for point in ranked:
            x=np.array([point['east_m'],point['north_m']])/1000
            if all(np.linalg.norm(x-s)>.4 for s in starts):starts.append(x)
            if len(starts)==4:break
        trials=[]
        for start in starts:
            result=minimize(lambda x:joint(arm,x),start,jac=True,method='SLSQP',bounds=[(-2,2)]*2,
                constraints=[dict(type='ineq',fun=lambda x:4.-np.dot(x,x),jac=lambda x:-2*x)],
                options=dict(maxiter=35,ftol=1e-7))
            value,grad=joint(arm,result.x)
            trials.append(dict(start_km=start,point_km=result.x,objective=value,gradient_per_km=grad,success=bool(result.success),message=str(result.message),iterations=int(result.nit)))
        best=min(trials,key=lambda r:r['objective']);x=np.asarray(best['point_km']);radius=np.linalg.norm(x)
        # Independently restart nuisances from each roof fit at the best site.
        rechecks=[]
        for s in ('A','B'):
            roof=engines[s,arm].fit([0,0]);before=engines[s,arm].fit(x)
            after=engines[s,arm].fit(x,'best-roof-restart',force_start=roof['vector'])
            rechecks.append(dict(scan=s,before=before['objective'],after=after['objective'],success=after['success']))
        neighborhood=[]
        for j in range(8):
            candidate=x+.025*np.array([np.sin(j*np.pi/4),np.cos(j*np.pi/4)])
            if np.linalg.norm(candidate)<=2.+1e-9:
                value,_=joint(arm,candidate);neighborhood.append(dict(point_km=candidate,objective=value))
        minima[arm]=dict(trials=trials,best=best,boundary_limited=bool(radius>1.999),radius_m=radius*1000,
            rechecks=rechecks,neighbors_25m=neighborhood)
        save(OUT/'minima-partial.json',minima)
    finish(engines,design,minima,time.monotonic()-started)
    profiles.shutdown()

def finish(engines,design,minima,elapsed):
    summary={};rows=[]
    for arm in ('fitted-c','zero-c'):
        summary[arm]={}
        for label in ('A','B','joint'):
            scans=('A','B') if label=='joint' else (label,)
            records=[]
            for p in design:
                en=np.array([p['east_m'],p['north_m']])/1000;fits=[engines[s,arm].fit(en,p['label']) for s in scans]
                roof=sum(engines[s,arm].fit([0,0])['objective'] for s in scans)
                r=dict(**p,scan=label,arm=arm,objective=sum(f['objective'] for f in fits),
                    delta_score=sum(f['objective'] for f in fits)-roof,success=all(f['success'] for f in fits))
                records.append(r);rows.append(r)
            lookup={(p['east_m'],p['north_m']):p for p in records}
            derivatives=[]
            for h in (50.,100.):
                derivatives.append(dict(step_m=h,gradient_per_100m=[(lookup[h,0.]['objective']-lookup[-h,0.]['objective'])/(2*h)*100,
                    (lookup[0.,h]['objective']-lookup[0.,-h]['objective'])/(2*h)*100]))
            summary[arm][label]=dict(roof_score=roof,derivatives=derivatives,best_sampled=min(records,key=lambda r:r['objective']),cells=records)
    save(OUT/'profile-summary.json',dict(summary=summary,minima=minima,elapsed_s=elapsed,scope=__doc__,seed=SEED,
        source_hashes={str(p):digest(p) for p in (Path(__file__),OUT/'A-profile-input.json',OUT/'B-profile-input.json',OUT/'A-profile-input.npz',OUT/'B-profile-input.npz')},
        joint='Shared position; independent scan nuisance parameters and timing priors. Sum of profiled negative log likelihood plus priors; lower is better.',
        limitations=['In-sample at known-site-selected candidate sets, not independent localization validation.','Current receiver baseline frozen and shared across RF arms; additional linear RX terms refitted.','Random stratified disk probes plus multistart local constrained optimization, not a global certificate.']))
    import csv
    with (OUT/'scores.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    plot(summary,minima)

def plot(summary,minima):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    limit=max(abs(c['delta_score']) for s in summary.values() for r in s.values() for c in r['cells'])
    fig,axes=plt.subplots(2,3,figsize=(15,11),sharex=True,sharey=True)
    for j,arm in enumerate(('fitted-c','zero-c')):
        for k,scan in enumerate(('A','B','joint')):
            ax=axes[j,k];r=summary[arm][scan];cells=r['cells'];g=np.array(r['derivatives'][0]['gradient_per_100m'])
            im=ax.scatter([c['east_m']/1000 for c in cells],[c['north_m']/1000 for c in cells],c=[c['delta_score'] for c in cells],cmap='RdBu_r',vmin=-limit,vmax=limit,s=45,edgecolors='.4')
            ax.plot(0,0,'k+',ms=13,mew=2,label='Known roof');ax.add_patch(plt.Circle((0,0),2,fill=False,ls=':',color='.5'))
            if np.linalg.norm(g)>0:ax.arrow(0,0,*(-g/np.linalg.norm(g)*.5),head_width=.10,width=.01,color='black',length_includes_head=True)
            if scan=='joint':
                m=minima[arm];p=np.array(m['best']['point_km']);ax.plot(*p,'*',ms=18,c='gold',mec='black',label='Best local search')
                ax.annotate(f"{m['radius_m']:.0f} m from roof\nΔscore {m['best']['objective']-r['roof_score']:+.1f}"+('\nBoundary-limited' if m['boundary_limited'] else ''),p,xytext=(5,12),textcoords='offset points',fontsize=9)
            ax.set_title(f'{scan} · {arm}\nGradient / 100 m: E {g[0]:+.2f}, N {g[1]:+.2f}',fontsize=11)
            ax.set(xlim=(-2.2,2.2),ylim=(-2.2,2.2),xlabel='East of roof (km)');ax.set_aspect('equal');ax.grid(alpha=.15)
            if k==0:ax.set_ylabel('North of roof (km)')
            ax.legend(fontsize=8,loc='upper left')
    fig.subplots_adjust(left=.07,right=.90,top=.85,bottom=.13,wspace=.24,hspace=.32)
    cax=fig.add_axes([.93,.20,.018,.58]);fig.colorbar(im,cax=cax,label='Profile score − own roof score (lower is better)')
    fig.suptitle('DS13 · top-response GLRT position profile within 2 km',fontsize=17,y=.97)
    fig.text(.5,.91,'Same observations/candidate union in both RF arms; known position shared across A+B; nuisance refit at every site',ha='center',fontsize=10)
    fig.text(.5,.04,'48 seeded random disk points + 16 boundary probes + roof and ±50/100 m cardinal probes.\nArrows: local downhill direction at roof. Stars: multistart constrained local search, not global-optimality proof.\nSaved receiver correction held fixed; additional RX offsets/drifts, common RF coefficient and satellite timing profiled.',ha='center',fontsize=10)
    fig.savefig(OUT/'position-profile-2km.png',dpi=170);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','smoke','run']);p.add_argument('--scan',choices=['A','B']);a=p.parse_args()
    if a.stage=='prepare':prepare(a.scan)
    elif a.stage=='smoke':smoke(a.scan)
    else:run()
