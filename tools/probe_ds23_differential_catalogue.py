"""All-causal-catalogue nominations from simultaneous CFO differences.

Receiver offsets cancel because both components use the same receiver/RF.
Phase tangents plus a regularized relative constant are proposal approximations;
full physical orbit-mode fits remain necessary before accepting identities.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from ds23_causal_phase_location import adjust_means
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_same_probe_IQ import OUT as RF
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_differential_catalogue'


def pair_screen(values,frequency,derivative,widths,noise):
    """Regularized phase/phase/constant Gaussian proposal, both CFO orders."""
    y=np.asarray(values);f,d=np.asarray(frequency),np.asarray(derivative)
    m,n=f.shape
    if d.shape!=f.shape or y.shape!=(n,) or np.asarray(widths).shape!=(m,) or noise<=0:
        raise ValueError('matching differential data and positive noise required')
    first=np.repeat(np.arange(m),m);second=np.tile(np.arange(m),m)
    prediction=f[second]-f[first]
    alias=np.rint((prediction.mean(axis=1)-y.mean())/PERIOD).astype(int)
    raw=y[None]+alias[:,None]*PERIOD-prediction
    design=np.stack((-d[first]*np.asarray(widths)[first,None],d[second]*np.asarray(widths)[second,None],np.full_like(raw,1000.)),axis=2)/noise
    gram=np.einsum('pni,pnj->pij',design,design)+np.eye(3)
    rhs=np.einsum('pni,pn->pi',design,raw/noise)
    coefficient=np.linalg.solve(gram,rhs[:,:,None])[:,:,0]
    residual=raw/noise-np.einsum('pni,pi->pn',design,coefficient)
    cost=np.sum(residual**2,axis=1)+np.sum(coefficient**2,axis=1)+np.linalg.slogdet(gram)[1]
    cost[first==second]=np.inf
    return dict(first=first,second=second,cost=cost,alias=alias,coefficient=coefficient,
        residual_RMS_hz=np.sqrt(np.mean((residual*noise)**2,axis=1)))


def run(case):
    scan,node,mask,powers,ordinary,hyper,entries,signed,_=context_signed(case)
    all_labels=list(range(len(scan.norads)));widths,receipts=phase_widths(scan,all_labels)
    means=forecast_phase_mean(receipts,hyper['shrinkage'])
    if signed['accepted']:means=adjust_means(means,receipts,hyper,signed['selection'])
    widths=np.asarray(widths)*hyper['multiplier'];means=np.asarray(means)
    rf=read(RF/'evaluation.json');selected=next(r for r in read(RF/'protocol.json')['selected'] if r['case']==case)
    rows=sorted([r for r in rf['rows'] if r['case']==case and r['status']=='complete'],key=lambda r:r['time_s'])
    times=np.array([r['time_s'] for r in rows]);values=np.array([r['refined_second_value']-r['refined_first_value'] for r in rows])
    # Source summaries accidentally reuse RF_qualified for both count and
    # statistics. Select the explicitly named all-refined statistic here.
    noise=rf['summary'][case]['all_refined']['difference_sigma_hz']
    positions={'regional_centre':np.zeros(2),'current_scan_RF_mode':np.asarray(signed['policy_arms']['c0']['endpoint_east_north_km'])}
    result={};flat_times=np.tile(times,len(all_labels));labels=np.repeat(np.arange(len(all_labels)),len(times))
    for name,position in positions.items():
        def geometry(phases):
            f,e=paired_phase_frequency(scan.sky,flat_times,labels,phases,*latlon(position))
            return f.reshape(len(all_labels),-1)*selected['lane'][2]/11.5e9,e.reshape(len(all_labels),-1)
        f,e=geometry(means);plus,_=geometry(means+.01);minus,_=geometry(means-.01)
        derivative=(plus-minus)/.02
        visible=np.flatnonzero(e.min(axis=1)>=0)
        screen=pair_screen(values,f[visible],derivative[visible],widths[visible],noise)
        phase_first=means[visible[screen['first']]]+widths[visible[screen['first']]]*screen['coefficient'][:,0]
        phase_second=means[visible[screen['second']]]+widths[visible[screen['second']]]*screen['coefficient'][:,1]
        screen['cost'][(abs(phase_first)>15)|(abs(phase_second)>15)]=np.inf
        offered=[]
        for k in np.argsort(screen['cost'])[:20]:
            if not np.isfinite(screen['cost'][k]):continue
            j1,j2=int(visible[screen['first'][k]]),int(visible[screen['second'][k]])
            offered.append(dict(first_index=j1,second_index=j2,first_norad=int(scan.norads[j1]),second_norad=int(scan.norads[j2]),
                score=float(screen['cost'][k]),RMS_hz=float(screen['residual_RMS_hz'][k]),difference_alias=int(screen['alias'][k]),
                phase_first_s=float(phase_first[k]),phase_second_s=float(phase_second[k]),relative_bias_hz=float(1000*screen['coefficient'][k,2])))
        result[name]=dict(position_east_north_km=position,visible_candidates=len(visible),all_ordered_distinct_pairs=len(visible)*(len(visible)-1),candidates=offered)
        print(case,name,[(r['first_norad'],r['second_norad'],round(r['RMS_hz'],2)) for r in offered[:5]],flush=True)
    record=dict(case=case,results=result,RF_noise_sigma_hz=noise,
        RF_evaluation_sha256=sha(RF/'evaluation.json'),
        all_causal_candidates_considered_no_satellite_whitelist=True,GPS_used=False,
        phase_tangent_Gaussian_screen_omits_physical_orbit_modes=True,
        nomination_not_final_satellite_association_or_position_gain=True)
    write(OUT/(case+'.json'),record);return record


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(cases=['DS23-0202','DS23-0274'],RF_evaluation_sha256=sha(RF/'evaluation.json'),
        positions=['regional_centre','current_scan_RF_mode'],all_causal_catalogue=True,
        signed_causal_phase_centres_and_widths=True,maximum_phase_s=15,relative_constant_sigma_hz=1000,
        workers=2,source_sha256=sha(Path(__file__)),no_GPS_used=True)
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('differential nomination protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(run,c) for c in protocol['cases']]):f.result()


if __name__=='__main__':main()
