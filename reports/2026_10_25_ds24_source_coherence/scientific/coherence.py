"""All-100-point source allocations, normalized priors, cached one-phase law."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import sys
import time
import traceback
import numpy as np
from scipy.linalg import solve_triangular
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp,roots_legendre

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=Path('/srv/bulk/leo/research/ds24-ch5-prediction-r01/prediction')
sys.path.insert(0,str(OLD))
import prediction02 as p
sr,k,r=p.sr,p.k,p.r
ARMS=('c0','fitted_c')
CUTS=(14,21,29)
LOCAL_CAP=512
TAIL_CAP=8192
CAP=600.
CLASSES=('whole_physical','whole_polynomial','split','piecewise_polynomial')


def write(name,value):r.write_new(HERE/name,value)
def npz(name,**arrays):
    path=HERE/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:np.savez_compressed(stream,**arrays)


def allocations(times,period=k.PERIOD):
    """Only native index defines cuts; one W constant and alias across pieces."""
    times=np.asarray(times);n=len(times)
    def polynomial(parts):
        columns=np.zeros((n,5*len(parts)))
        for index,use in enumerate(parts):
            t=times[use]
            if len(t)<5 or np.ptp(t)<=0:raise ValueError('fixed polynomial segment invalid')
            z=2*(t-t.min())/np.ptp(t)-1
            columns[use,5*index:5*index+5]=np.polynomial.legendre.legvander(z,4)*period/np.sqrt(6)
        return columns
    allpoints=np.arange(n)
    rows=[dict(name='whole_physical',family='whole_physical',mask=np.ones(n,bool),poly=np.zeros((n,0)),cut=None,allocation='whole',log_within_prior=0.),
        dict(name='whole_polynomial',family='whole_polynomial',mask=np.zeros(n,bool),poly=polynomial([allpoints]),cut=None,allocation='whole',log_within_prior=0.)]
    for cut in CUTS:
        prefix,suffix=np.arange(cut),np.arange(cut,n)
        for label,physical,unresolved in [('prefix',prefix,suffix),('suffix',suffix,prefix)]:
            mask=np.zeros(n,bool);mask[physical]=True
            rows.append(dict(name='cut'+str(cut)+'_'+label,family='split',mask=mask,poly=polynomial([unresolved]),
                cut=cut,allocation=label,log_within_prior=-np.log(6)))
        rows.append(dict(name='cut'+str(cut)+'_polynomial',family='piecewise_polynomial',mask=np.zeros(n,bool),poly=polynomial([prefix,suffix]),
            cut=cut,allocation='both_unresolved',log_within_prior=-np.log(3)))
    # Controls first, scientifically uninformative all-physical extreme last.
    order=['whole_polynomial']+['cut'+str(c)+'_polynomial' for c in CUTS]+['cut'+str(c)+'_'+a for c in CUTS for a in ('prefix','suffix')]+['whole_physical']
    return [next(row for row in rows if row['name']==name) for name in order]


class Geometry:
    """Exact propagated rows cached by requested float phase; no interpolation."""
    def __init__(self,d,x):self.d=d;self.x=x;self.cache={};self.propagated_nodes=0
    def __call__(self,phases):
        phases=np.asarray(phases,float)
        missing=list(dict.fromkeys(float(v) for v in phases if float(v) not in self.cache))
        for start in range(0,len(missing),256):
            batch=np.asarray(missing[start:start+256]);geo=k.m.q.phase_geometry(self.d,self.x,batch)
            for index,value in enumerate(batch):self.cache[float(value)]=(geo['frequency_hz'][index],geo['shape_columns_hz'][index],geo['elevation_deg'][index])
            self.propagated_nodes+=len(batch)
        return dict(frequency_hz=np.stack([self.cache[float(v)][0] for v in phases]),
            shape_columns_hz=np.stack([self.cache[float(v)][1] for v in phases]),
            elevation_deg=np.stack([self.cache[float(v)][2] for v in phases]))


def kernel(comp,geometry,prior,phases):
    """Positive Woodbury quadratic for all81aliases, vectorized over aliases."""
    phases=np.asarray(phases);geo=geometry(phases)
    raw=comp['raw'][None]-geo['frequency_hz']*comp['q'][None]
    shape=geo['shape_columns_hz']*comp['q'][None,:,None]
    n,m,rank=shape.shape
    white=solve_triangular(comp['root'],raw.T,lower=True).T
    wb=solve_triangular(comp['root'],shape.transpose(1,0,2).reshape(m,-1),lower=True).reshape(m,n,rank).transpose(1,0,2)
    gram=np.eye(rank)[None]+np.einsum('nki,nkj->nij',wb,wb)
    values=white[:,None]+comp['whitened_aliases'][None]
    rhs=np.einsum('nki,nak->nai',wb,values)
    coefficient=np.linalg.solve(gram[:,None],rhs[...,None])[...,0]
    residual=values-np.einsum('nki,nai->nak',wb,coefficient)
    energy=np.sum(residual**2,axis=2)+np.sum(coefficient**2,axis=2)
    logdet=comp['base_logdet']+np.linalg.slogdet(gram)[1]
    return logsumexp(-.5*(energy+logdet[:,None]+m*np.log(2*np.pi)),axis=1)-np.log(len(comp['aliases']))+prior['distribution'].logpdf(phases)-np.log(prior['mass'])


def model_component(base,row):
    mask=np.r_[np.ones(57,bool),row['mask']]
    columns=np.vstack((np.zeros((57,row['poly'].shape[1])),row['poly']))
    covariance=base['covariance']+columns@columns.T
    root=np.linalg.cholesky(covariance)
    q=base['q']*mask
    comp=dict(base,root=root,covariance=covariance,q=q,base_logdet=float(2*np.log(np.diag(root)).sum()),
        whitened_aliases=solve_triangular(root,base['shifts'].T,lower=True).T)
    return comp,columns


def discovery_component(base):
    comp=dict(base,d=dict(base['d'],target_track=dict(times=base['times'][:57],rf_hz=11.5e9)),
        raw=base['raw'][:57],covariance=base['covariance'][:57,:57],q=base['q'][:57])
    comp['root']=np.linalg.cholesky(comp['covariance'])
    comp['base_logdet']=float(2*np.log(np.diag(comp['root'])).sum())
    comp['aliases'],comp['shifts']=k.alias_vectors(np.zeros(57,int),np.arange(-4,5))
    comp['whitened_aliases']=solve_triangular(comp['root'],comp['shifts'].T,lower=True).T
    return comp


def D_geometry(geometry):
    def evaluate(phases):
        geo=geometry(phases)
        return dict(frequency_hz=geo['frequency_hz'][:,:57],shape_columns_hz=geo['shape_columns_hz'][:,:57],elevation_deg=geo['elevation_deg'][:,:57])
    return evaluate


def integrate(comp,geometry,prior,pieces,order,deadline):
    z,w=roots_legendre(order);pieces=np.asarray(pieces)
    half=np.diff(pieces,axis=1)[:,0]/2;center=pieces.mean(axis=1)
    phases=(center[:,None]+half[:,None]*z).ravel()
    weights=(np.log(half[:,None])+np.log(w)[None]).ravel()
    logs=[]
    for start in range(0,len(phases),128):
        sr.alarm(deadline-time.monotonic())
        logs.append(kernel(comp,geometry,prior,phases[start:start+128]))
    return float(logsumexp(np.concatenate(logs)+weights))


def modes(comp,geometry,prior,window,deadline):
    grid=np.linspace(*window,257)
    values=np.concatenate([kernel(comp,geometry,prior,grid[start:start+128]) for start in range(0,len(grid),128)])
    indices=[i for i in range(1,len(grid)-1) if values[i]>=values[i-1] and values[i]>=values[i+1]]
    indices=sorted(indices,key=lambda i:-values[i])[:3]
    if not indices:indices=[int(np.argmax(values))]
    result=[]
    for index in indices:
        sr.alarm(deadline-time.monotonic())
        lo,hi=grid[max(0,index-1)],grid[min(len(grid)-1,index+1)]
        fun=lambda phi:-float(kernel(comp,geometry,prior,np.array([phi]))[0])
        optimum=minimize_scalar(fun,bounds=(lo,hi),method='bounded',options=dict(maxiter=60,xatol=1e-6))
        mean=float(optimum.x);h=min(.001,(mean-window[0])/2,(window[1]-mean)/2)
        curvature=(fun(mean+h)+fun(mean-h)-2*fun(mean))/h**2 if h>0 else 0.
        width=float(np.clip(1/np.sqrt(curvature) if curvature>0 else .1,1e-4,.5))
        result.append(dict(center_s=mean,scale_s=width,numerical_search_success=bool(optimum.success),log_density=-fun(mean)))
    return result


def local_bounds(d,comp,geometry,prior,pieces,deadline,stop_below=None):
    pieces=np.asarray(pieces,float).reshape(-1,2)
    if len(pieces)>LOCAL_CAP:return dict(resolved=False,reason='initial common panels exceed512',panels=len(pieces))
    def evaluate(part):
        lows=[];highs=[]
        for start in range(0,len(part),128):
            sr.alarm(deadline-time.monotonic())
            a,b=sr.sb.physical_panel_bounds(d,comp,geometry,prior,part[start:start+128]);lows.append(a);highs.append(b)
        return np.concatenate(lows),np.concatenate(highs)
    lower,upper=evaluate(pieces)
    while True:
        lo,hi=float(logsumexp(lower)),float(logsumexp(upper))
        excluded=stop_below is not None and hi<stop_below
        if 2*(hi-lo)<=1e-3 or excluded or len(pieces)>=LOCAL_CAP:break
        uncertainty=upper+np.log(-np.expm1(np.minimum(0.,lower-upper)))
        count=min(64,LOCAL_CAP-len(pieces),len(pieces));chosen=np.argsort(uncertainty)[-count:]
        keep=np.ones(len(pieces),bool);keep[chosen]=False
        old=pieces[chosen];middle=old.mean(axis=1)
        new=np.vstack((np.column_stack((old[:,0],middle)),np.column_stack((middle,old[:,1]))))
        a,b=evaluate(new);pieces=np.vstack((pieces[keep],new));lower=np.r_[lower[keep],a];upper=np.r_[upper[keep],b]
    return dict(resolved=True,lower_log_integral=lo,upper_log_integral=hi,objective_width=2*(hi-lo),panels=len(pieces),
        absolute_precision=bool(2*(hi-lo)<=1e-3),stopped_for_exclusion=bool(excluded))


def classes(rows,tail_upper=None):
    result=[]
    for family in CLASSES:
        group=[row for row in rows if row['family']==family]
        count={'whole_physical':1,'whole_polynomial':1,'split':6,'piecewise_polynomial':3}[family]
        if len(group)!=count or any(not row.get('bounds',{}).get('resolved') for row in group):
            result.append(dict(family=family,status='unresolved'));continue
        lower=float(logsumexp([row['bounds']['lower_log_integral']+row['log_within_prior'] for row in group]))
        upper=float(logsumexp([row['bounds']['upper_log_integral']+row['log_within_prior'] for row in group]))
        point=float(logsumexp([row['log_integral64']+row['log_within_prior'] for row in group]))
        full_upper=float(np.logaddexp(upper,tail_upper)) if tail_upper is not None else None
        result.append(dict(family=family,status='bounded' if full_upper is not None else 'window_only',
            lower_log_evidence=lower,upper_log_evidence=full_upper,window_upper_log_evidence=upper,window_log_evidence=point,
            window_objective=-2*point,normalized_cells=count,class_prior=.25,
            within_class_window_weights={row['name']:float(np.exp(row['log_integral64']+row['log_within_prior']-point)) for row in group}))
    return result


def ordering(group):
    if len(group)!=4 or any(row.get('status')!='bounded' or not np.isfinite([row['lower_log_evidence'],row['upper_log_evidence']]).all()
        or row['lower_log_evidence']>row['upper_log_evidence'] for row in group):return dict(proved=False,reason='full evidence bound unresolved')
    for winner in group:
        other=max(row['upper_log_evidence'] for row in group if row['family']!=winner['family'])
        if winner['lower_log_evidence']>other:
            return dict(proved=True,winner=winner['family'],minimum_log_evidence_margin=winner['lower_log_evidence']-other,
                identity_assignment=False,portion_adoption=False,absolute_precision_implied=False)
    return dict(proved=False,reason='class evidence bounds overlap')


def load(arm):
    archived=OLD/'run02'/arm
    with np.load(archived/'joint_background.npz') as saved:
        ix=np.r_[np.arange(57),np.arange(81,124)]
        base=dict(raw=saved['raw_hz'][ix].copy(),covariance=saved['covariance_hz2'][np.ix_(ix,ix)].copy(),
            q=saved['native_q'][ix].copy(),x=saved['common_position_east_north_km'].copy(),
            native_ids=saved['native_ids'][ix].copy(),times=saved['times_s'][ix].copy())
    d=r.context('DS24-0013')
    discovery=r.read(p.w.OLD/'owner1/metadata.json')
    d['original_protected']=set(d['original_protected'])-set(discovery['exact_candidate_indices'])
    cd=k.candidate(p.w.owner_context(d,discovery),57450)
    cd['target_track']=dict(times=base['times'],rf_hz=11.5e9)
    target=cd['target'];old=r.read(OLD/'run02'/arm/'D_evidence.json')
    if abs(target['phase_mean_s']-old['original_phase_location_s'])>1e-12 or abs(target['phase_sd_s']-old['original_phase_sd_s'])>1e-12:
        raise ValueError('original causal phase prior changed')
    root=np.linalg.cholesky(base['covariance'])
    aliases,shifts=k.alias_vectors(np.r_[np.zeros(57,int),np.ones(43,int)],np.arange(-4,5))
    meta=d['scan'].fixed_window_noise
    sigma=np.array([meta['per_observation_noise_sigma_hz'][oid] if meta['extra_parameter_BIC_gain']>0 else d['scan'].radio_sigma_hz for oid in base['native_ids']])
    if np.any(sigma<=0) or np.any(base['q']<=0):raise ValueError('native RF/noise contract invalid')
    base.update(d=cd,root=root,aliases=aliases,shifts=shifts,whitened_aliases=solve_triangular(root,shifts.T,lower=True).T,
        base_logdet=float(2*np.log(np.diag(root)).sum()),noise_minimum_sd=float(np.min(sigma)*np.sqrt(2)),
        observer=sr.geodetic_to_ecef_km(*k.latlon(base['x']),0.),native_sigma_Hz=sigma)
    support=r.read(archived/'CH4_same_support.json')
    dsupport=r.read(archived/'D_support.json')
    for saved in (support,dsupport):
        if not saved['certified'] or saved['root_brackets'] or saved['inner_visible_intervals']!=[[-15.,15.]]:
            raise ValueError('archived full-domain nominal support required; no support rescue')
    posterior=r.read(archived/'Dposterior.json')['GL64']
    window=np.array([max(-15.,posterior['phase_mean_s']-24*posterior['phase_SD_s']),min(15.,posterior['phase_mean_s']+24*posterior['phase_SD_s'])])
    return cd,base,support,dsupport,window


def job(arm,deadline):
    began=time.monotonic();rows=[]
    try:
        sr.alarm(deadline-time.monotonic());cd,base,support,dsupport,window=load(arm)
        geometry=Geometry(cd,base['x']);prior=sr.law(cd)
        models=allocations(base['times'][57:])
        comps={row['name']:model_component(base,row)[0] for row in models}
        npz(Path(arm)/'inputs.npz',raw_hz=base['raw'],covariance_hz2=base['covariance'],native_q=base['q'],native_sigma_Hz=base['native_sigma_Hz'],
            native_ids=base['native_ids'],times_s=base['times'],common_position_east_north_km=base['x'],aliases=base['aliases'],window_s=window)
        cuts=list(np.asarray(support['interpolation_breakpoints']))
        proposals={}
        for model in models:
            sr.alarm(deadline-time.monotonic());found=modes(comps[model['name']],geometry,prior,window,deadline);proposals[model['name']]=found
            for mode in found:
                cuts.extend(mode['center_s']+mode['scale_s']*np.array([-8,-3,-1,0,1,3,8]))
        pieces=sr.sg.panels([list(window)],np.asarray(sorted(set(cuts))))
        if len(pieces)>LOCAL_CAP:raise ValueError('common local panel count exceeds512; no cuts dropped')
        write(Path(arm)/'proposal.json',dict(window_s=window,window_is_computational_only=True,models=proposals,pieces=pieces,
            shared_geometry=True,remote_mass_renormalized=False,cuts=CUTS,class_priors={name:.25 for name in CLASSES}))
        dc=discovery_component(base)
        dfirst=integrate(dc,D_geometry(geometry),prior,pieces,32,deadline)
        dsecond=integrate(dc,D_geometry(geometry),prior,pieces,64,deadline)
        original_D=r.read(OLD/'run02'/arm/'D_evidence.json')['objective']
        derror=abs(-2*dsecond-original_D)
        write(Path(arm)/'D_replay.json',dict(original_D_objective=original_D,window_objective32=-2*dfirst,
            window_objective64=-2*dsecond,error=derror,quadrature_difference=2*abs(dfirst-dsecond),
            passed=bool(derror<=1e-3 and 2*abs(dfirst-dsecond)<=1e-3),same_archived_D_marginal=True))
        if derror>1e-3 or 2*abs(dfirst-dsecond)>1e-3:raise ValueError('original D evidence replay prerequisite failed')
        for model in models:
            comp=comps[model['name']]
            first=integrate(comp,geometry,prior,pieces,32,deadline)
            write(Path(arm)/(model['name']+'_primary.json'),dict(model=model['name'],log_integral32=first,window_objective=-2*first))
            second=integrate(comp,geometry,prior,pieces,64,deadline)
            row={key:value for key,value in model.items() if key not in ('mask','poly')}
            row.update(log_integral32=first,log_integral64=second,quadrature_difference_objective=2*abs(first-second),
                independent_quadrature_passed=bool(2*abs(first-second)<=1e-3),window_only=True)
            rows.append(row);write(Path(arm)/(model['name']+'_quadrature.json'),row)
        original=r.read(OLD/'run02'/arm/'CH4_mixed_evidence.json')['objective']
        replay=abs(-2*next(row['log_integral64'] for row in rows if row['name']=='whole_polynomial')-original)
        write(Path(arm)/'replay.json',dict(whole_polynomial_old_objective=original,window_objective_error=replay,passed=replay<=1e-3,
            D_evidence_reused_unchanged=True,parent_recalibrated=False))
        if replay>1e-3:raise ValueError('whole-null/D marginal replay prerequisite failed')
        bounded=[];best=-np.inf
        for row in sorted(rows,key=lambda q:-q['log_integral64']):
            sr.alarm(deadline-time.monotonic())
            bound=local_bounds(cd,comps[row['name']],geometry,prior,pieces,deadline,best-np.log(11) if np.isfinite(best) else None)
            row['bounds']=bound;bounded.append(row)
            if bound.get('resolved'):best=max(best,bound['lower_log_integral']+row['log_within_prior'])
            write(Path(arm)/(row['name']+'_bounds.json'),row)
        local_classes=classes(rows)
        best_lower=max(row['lower_log_evidence'] for row in local_classes if row.get('lower_log_evidence') is not None)
        # A single certified D-tail upper controls EVERY W allocation. W's
        # independent declared Gaussian native noise cannot be conditioned away.
        ceiling=float(-.5*(43*np.log(2*np.pi)+np.log(2*base['native_sigma_Hz'][57:]**2).sum()))
        tail_pieces=sr.sg.panels([[-15.,float(window[0])],[float(window[1]),15.]],np.asarray(dsupport['interpolation_breakpoints']))
        tail_geometry=Geometry(dc['d'],base['x'])
        sr.alarm(deadline-time.monotonic())
        tail=sr.sb.enclosure(dc['d'],dc,tail_geometry,prior,tail_pieces,best_lower-ceiling-np.log(1e6))
        upper=tail.get('upper_log_integral');remote=upper+ceiling if upper is not None else None
        write(Path(arm)/'remote_guard.json',dict(D_tail_enclosure=tail,native_W_Gaussian_log_density_ceiling=ceiling,
            global_joint_remote_upper_log_evidence=remote,remote_not_renormalized=True,
            Gaussian_noise_SD_multiplier=np.sqrt(2),Gamma_mixture_ceiling_claimed=False))
        group=classes(rows,remote)
        proof=ordering(group)
        if not all(row['independent_quadrature_passed'] for row in rows):
            proof=dict(proved=False,reason='at least one independent quadrature check failed; bounds retained',bound_only_diagnostic=proof)
        result=dict(arm=arm,status='complete',classes=group,models=rows,ordering=proof,remote_guard=remote,
            geometry_propagated_nodes=geometry.propagated_nodes,scientific_worker_seconds=time.monotonic()-began,
            all100IDs_scored=True,portion_adopted=False,identity_assignment=False,position_fits=0,GPS_used=False)
        write(Path(arm)/'result.json',result)
        print(arm,proof,flush=True)
    except Exception as exc:
        result=dict(arm=arm,status='budget_or_context_failed',error=repr(exc),traceback=traceback.format_exc(),
            completed_quadrature_models=[row['name'] for row in rows],scientific_worker_seconds=time.monotonic()-began,
            class_slots=[dict(family=name,status='unresolved') for name in CLASSES],
            model_slots=[dict(name=name,status='partial_or_missing') for name in ['whole_physical','whole_polynomial']+
                ['cut'+str(c)+'_'+a for c in CUTS for a in ('prefix','suffix','polynomial')]],
            position_fits=0,GPS_used=False)
        write(Path(arm)/'failure.json',result)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    return result


def verify(approval=False):
    protocol=r.read(HERE/'protocol.json');digest=r.sha(HERE/'protocol.json')
    if digest!=r.read(HERE/'protocol_seal.json')['protocol_sha256']:raise ValueError('protocol changed')
    for path,h in protocol['source_input_hashes'].items():
        if r.sha(path)!=h:raise ValueError('source/input changed: '+path)
    if approval:
        receipt=r.read(ROOT/'audit/preflight.json')
        if receipt.get('all_passed') is not True or receipt.get('protocol_sha256')!=digest:raise ValueError('matching independent preflight required')
    return protocol


def freeze():
    bindings=dict(r.read(OLD/'run02/protocol.json')['source_input_hashes'])
    for path,h in r.read(OLD/'run02/RF_seal.json')['files'].items():
        if r.sha(path)!=h:raise ValueError('archived prediction artifact changed')
        bindings[path]=h
    for path in (Path(__file__),HERE/'test_coherence.py',HERE/'PROTOCOL.md',HERE/'test_receipt.json',ROOT/'COORDINATOR_PLAN.md',OLD/'run02/RF_seal.json',
        OLD/'capsule.json',OLD/'prediction02.py',OLD/'run02/protocol.json'):
        bindings[str(path)]=r.sha(path)
    protocol=dict(cuts_after_W_indices=CUTS,classes=CLASSES,class_prior=.25,split_allocation_prior='uniform6cells',piecewise_null_prior='uniform3cuts',
        source_input_hashes=bindings,observations='D57+W43 all100 always; archivedradio/noise/background/commonc0RFx unchanged',
        segment_polynomial='localownsegmenttimescaled[-1,1],Legendre0..4×PERIOD/sqrt6; independentGaussianunitcoefficients',
        aliases='oneDalias andoneWalias uniform−4..4,81joint; ONE W300Hzconstant acrosssegments; graphgaugeunchanged',
        physical='one57450phase+3physicalmodes sharedD+physicalWrows; no secondorbitintegral',
        phase_integration='exactdirectphase density; computationalwindow archivedDmean±24SD; no prior/window renormalization',
        numerical_proposals='257pointjointpilot,up to3localmodes/model,affinecenter±{0,1,3,8}scale,unioncommonbankpieces/cache; boundedmodeoptimization60iter',
        quadrature='independentGL32/64oncommonmode/bankpanels; objectiveagreement<=1e-3; no hidden-mode guarantee from agreementalone',
        local_bounds=dict(max_panels=512,refinement_batch=64,original_physical_derivative_envelopes=True),
        remote_bounds='certifiedDtail evidence upper ×(2π)^(-43/2)prod(1/(sqrt2σ_W)), originalDtail8192cap; noGamma-mixturepeakclaim',
        remote_stop='upperjointremotemass<bestclasslocallower×1e-6 isrefinementtarget,notrequiredordergate; anyvalidfinitefullboundsmayproveorder; no growth/rescue',
        required_replay='originalD andwhole-Wpoly jointscore within1e-3; DGL32/64agreement1e-3; identicalDbackground/prior law',
        scientific_seconds=600,workers=2,BLAS_threads=1,worker_deadline_seconds=300,scientific_retries=0,
        phase_prior='originalStudentnu3conditioned[-15,+15]s,originalnormalization/fullB(phi)preserved',
        support='archived57450D+Wfull-phaseLOS certified; anysubsetinheritsfullnominalsupport',
        eligibility='diagnosticphysicalportion not originalcurvedsalvageadmission; no gate/support waiver or prefixadoption',
        position_fits=0,GPS_used=False,new_RF=0,operational_identity_assignment=False)
    write('protocol.json',protocol);write('protocol_seal.json',dict(protocol_sha256=r.sha(HERE/'protocol.json')))
    print(r.sha(HERE/'protocol.json'),flush=True)


def run():
    verify(True)
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if r.os.environ.get(name)!='1':raise ValueError('one numerical thread required')
    write('execution_started.json',dict(protocol_sha256=r.sha(HERE/'protocol.json')))
    start=time.monotonic();deadline=start+300;results=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(job,arm,deadline):arm for arm in ARMS}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(arm=futures[future],status='worker_failed',error=repr(exc),scientific_worker_seconds=300,
                class_slots=[dict(family=name,status='unresolved') for name in CLASSES]))
    verify(True)
    write('execution.json',dict(arms=results,scientific_seconds=sum(row['scientific_worker_seconds'] for row in results),wall_seconds=time.monotonic()-start,
        cap_seconds=600,all_selected_terminal=True,selected_arms=2,selected_classes=8,selected_model_contexts=22,all100IDs_retained=True,position_fits=0,GPS_used=False))
    files={str(path):r.sha(path) for path in sorted(HERE.rglob('*')) if path.is_file() and not set(path.parts)&{'__pycache__','.pytest_cache'}}
    write('RF_seal.json',dict(files=files,protocol_sha256=r.sha(HERE/'protocol.json'),all_selected_terminal=True,position_fits=0,GPS_used=False))
    print('TERMINAL',r.read(HERE/'execution.json')['scientific_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'));args=parser.parse_args()
    freeze() if args.action=='freeze' else run()
