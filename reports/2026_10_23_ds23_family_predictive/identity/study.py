"""Symmetric union-family-held-out predictive comparison; RF positions fixed."""
from pathlib import Path
import argparse
import signal
import time
import numpy as np
import mechanism as m
from build_dsx01_orbit_modes import build_modes
from ds23_conditioned_relative_nomination import gaussian_prediction
from ds23_family_cavity import coarse_phase_scores
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from ds23_temporal_predictive_recovery import calibration
from dsx01_inference_audit import validate_elements
from probe_ds23_linear_family_groups import residual_checks
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from run_algo01_ds23_sample import read,write,sha

OUT=Path(__file__).resolve().parent
OLD=Path('/srv/bulk/leo/research/algo04-native-qualification-20261023/identity0259')

def union_keep(p,pool):
    keep=p.keep.copy()
    for row,sl in zip(p.rows,p.slices,strict=True):
        if row['candidate_index'] in pool:keep[sl]=False
    return keep

def freeze():
    families={};inputs={}
    for family,suffixes in [(65340,['001','002','005','007']),(67618,['006'])]:
        candidates=set()
        for suffix in suffixes:
            path=OLD/(suffix+'.json');d=read(path);inputs[str(path)]=sha(path)
            candidates.update(int(d['catalogue_norads'][j]) for j in d['candidate_pool'])
        families[str(family)]=dict(suffixes=suffixes,norads=sorted(candidates))
    for path in [m.FROZEN/'raw/DS23-0259/result.json',m.FROZEN/'raw/DS23-0259/native/DS23-0259.json',m.FROZEN/'raw/DS23-0259/native/DS23-0259_persistent5s_selection.json']:inputs[str(path)]=sha(path)
    protocol=dict(families=families,arms=list(m.ARMS),positions=['graph_parent','native_RF_endpoint'],job_cap_s=180,total_budget_s=600,
        candidate_selection='Frozen previous-screen union per target: original plus all previous automatic candidates; no manualNORADchoice',
        calibration='All retained curved observations assigned any shortlisted original/replacement family withheld in every comparison; other families calibrate;5fixed-position phase refreshes',
        evidence='All nativepaths oftestedfamily jointly predictive; withheld curved observations never calibrate or enter tested evidence; no original/replacement phase/mode posterior reuse',
        symmetric_prior='Fresh causal phase mean/width policy per candidate plus3physical orbit modes withzero mean/unitvariance;300Hz independent pathoffset; shared curved-only radio posterior covariance',
        alias='Oneinteger alias percompletepath fromsamecoarseGaussian rule; prior equal across identities',
        exact_refinement='5exactphasegeometryrefreshes,±15sphase,elevation>=0,phaseconvergence<=.01;fixed-radio residualgates separatelydiagnostic',
        coarse_catalogue='All1338phase-onlydiagnostic; never silently add candidates whose calibration was not held out',
        limitations='RFpositionconditioned,notcrossvalidation; momentmatchedGaussian phaseprior; finite frozen shortlist; covariance/prior approximation; no localization accuracy inference',
        no_GPS_future_TLE_new_RF_or_position_fit=True,input_hashes=inputs,source_sha256=sha(Path(__file__)))
    path=OUT/'protocol.json'
    if path.exists():assert read(path)==protocol
    else:write(path,protocol)
    return protocol

def prediction(d,data,j,aliases):
    nb=data['radio_width'];ng=len(data['members']);bank=dict(time_s=d['scan'].sky['time_s'],position_km=d['scan'].sky['position_km'][[j]],velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
    modes=build_modes(d['scan'],[j],[j],'physical')[0]
    mean=np.r_[data['coefficient'][:nb],d['all_means'][j]/d['widths'][j],np.zeros(3+ng)]
    covariance=np.eye(len(mean));covariance[:nb,:nb]=data['covariance'][:nb,:nb];covariance[-ng:,-ng:]=np.eye(ng)*300**2
    values=data['values']+np.asarray(aliases)[data['groups']]/4.4e-6
    constants=np.eye(ng)[data['groups']]
    def geometry(phase):
        f,e=phase_frequency_grid(bank,data['times'],*latlon(d['x']),phase_seconds=phase)
        plus=phase_frequency_grid(bank,data['times'],*latlon(d['x']),phase_seconds=phase+.01)[0]
        minus=phase_frequency_grid(bank,data['times'],*latlon(d['x']),phase_seconds=phase-.01)[0]
        derivative=(plus[0]-minus[0])/.02
        orbit=paired_frequency_modes(bank,modes,data['times'],np.zeros(len(data['times']),int),np.array([phase]),*latlon(d['x']))
        return data['q']*(f[0]-derivative*phase),np.column_stack((data['radio'],data['q']*derivative*d['widths'][j],data['q'][:,None]*orbit,constants)),e[0]
    reference=float(d['all_means'][j]);history=[]
    for _ in range(5):
        intercept,features,e=geometry(reference)
        result=gaussian_prediction(values-intercept-features@mean,features,covariance,data['noise'])
        coefficient=mean+result['parameter_update'];phase=float(coefficient[nb]*d['widths'][j]);change=abs(phase-reference);history.append(change);reference=float(np.clip(phase,-15,15))
    if abs(phase)<=15:
        intercept,features,e=geometry(phase);residual=values-intercept-features@coefficient
    else:e=np.full(len(values),-90.);residual=result['native_residual']
    r=dict(candidate_index=j,norad=int(d['scan'].norads[j]),score=result['objective'],phase_s=phase,phase_change_s=change,
        minimum_elevation_deg=float(e.min()),aliases=aliases,conditional_RMS_hz=float(np.sqrt(np.mean(residual**2))),
        qualified=bool(abs(phase)<=15 and e.min()>=0 and change<=.01),residual_hz=residual,coefficient=coefficient,
        prior_mean=mean,prior_covariance=covariance,physical_modes=True,phase_prior_mean_s=float(d['all_means'][j]),phase_prior_width_s=float(d['widths'][j]),
        phase_and_modes_never_reuse_calibration=True,phase_history=history)
    r['fixed_radio_checks']=residual_checks(data,r)
    r['physical_and_residual_qualified']=bool(r['qualified'] and all(v['compatible'] for v in r['fixed_radio_checks']))
    return r

def run(family,arm,position):
    started=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180sjobcap')));signal.alarm(180)
    result=dict(family=family,arm=arm,position=position,status='failed')
    try:
        protocol=read(OUT/'protocol.json');parent,kind,fragments,record=m.load('DS23-0259')
        scan=parent['scan'];cutoff=scan.receipt['cutoff_utc_ns']
        for element in scan.elements.values():validate_elements(element,cutoff)
        pool=[int(np.where(scan.norads==n)[0][0]) for n in protocol['families'][str(family)]['norads']]
        selected=[f for f in fragments if f['norad']==family];d=m.append(parent,selected)
        target=int(np.where(scan.norads==family)[0][0])
        saved=(record['ordinary_graph']['arms'] if position=='graph_parent' else read(m.FROZEN/'raw/DS23-0259/native/DS23-0259.json')['methods']['persistent5s']['arms'])[arm]
        x=np.asarray(saved['endpoint_east_north_km']);reference=np.asarray(saved['phase_reference'])
        base=m.exp.paths.build(d,kind,arm,reference);keep=union_keep(base,set(pool));d=dict(d,keep=keep,entries=[],x=x)
        history=[]
        for _ in range(5):
            p=m.exp.paths.build(d,kind,arm,reference);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            history.append(float(np.max(abs(phase-reference))));reference=phase
        c,covariance=calibration(p,x,d['powers']);nb=p.hardware.shape[1]+p.smooth.shape[1]
        # Dummy phase labels affect only discarded non-radio geometry columns.
        entries=[dict(track_index=len(scan.tracks)+k,candidate_index=target,alias=0) for k in range(len(selected))]
        view,values,sigma,groups,slices=linear_geometry(p,entries);geometry=geometry_features(view,x,0.);radio=geometry['features'][:,:nb]
        members=[dict(component=d['scan'].tracks[e['track_index']]['key'],track_index=e['track_index'],points=e['points'] if 'points' in e else len(d['scan'].tracks[e['track_index']]['times']),observation_ids=d['scan'].tracks[e['track_index']]['observation_ids']) for e in entries]
        fitids={oid for i,sl in zip(p.members,p.slices,strict=True) for oid,use in zip(p.scan.tracks[i]['observation_ids'],keep[sl],strict=True) if use}
        heldids={oid for member in members for oid in member['observation_ids']};assert not fitids&heldids
        assert all(not keep[sl].any() for row,sl in zip(p.rows,p.slices,strict=True) if row['candidate_index'] in pool)
        noise=sigma*np.sqrt(2);basecov=np.diag(noise**2)+radio@covariance[:nb,:nb]@radio.T+300**2*(groups[:,None]==groups[None,:])
        data=dict(p=p,coefficient=c['coefficient'],covariance=covariance,radio_width=nb,times=view.flat_times,values=values,q=view.q,radio=radio,noise=noise,groups=groups,members=members,slices=slices)
        f,e=phase_frequency_grid(p.scan.sky,data['times'],*latlon(x),phase_seconds=d['all_means'])
        plus=phase_frequency_grid(p.scan.sky,data['times'],*latlon(x),phase_seconds=d['all_means']+.01)[0]
        minus=phase_frequency_grid(p.scan.sky,data['times'],*latlon(x),phase_seconds=d['all_means']-.01)[0]
        coarse=coarse_phase_scores(values,radio@c['coefficient'][:nb],data['q']*f,data['q']*(plus-minus)/.02,d['widths'],basecov,groups)
        scores=np.where(e.min(axis=1)>=0,coarse['score'],np.inf)
        candidates=[prediction(d,data,j,coarse['aliases'][j]) for j in pool];candidates.sort(key=lambda r:r['score'])
        result.update(status='complete',candidates=candidates,candidate_norads=protocol['families'][str(family)]['norads'],
            original=next(r for r in candidates if r['norad']==family),members=members,held_observation_ids=sorted(heldids),
            calibration_IDs=sorted(fitids),calibration_points=len(fitids),removed_calibration_points=int(parent['keep'].sum()-keep.sum()),
            held_fit_ID_overlap=0,all_shortlist_family_curved_points_withheld=True,causal_elements_verified=len(scan.elements),
            calibration_phase_changes_s=history,calibration_phase_converged=history[-1]<=.01,
            endpoint_east_north_km=x,coarse_catalogue_count=len(scores),coarse_top10=[dict(norad=int(scan.norads[j]),score=float(scores[j]),in_frozen_exact_pool=j in pool) for j in np.argsort(scores)[:10] if np.isfinite(scores[j])])
    except Exception as exc:
        import traceback
        result.update(error=repr(exc),traceback=traceback.format_exc())
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(OUT/(f'{family}_{arm}_{position}.json'),result);print(result['status'],family,arm,position,result['seconds'],result.get('error'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--family',type=int);parser.add_argument('--arm');parser.add_argument('--position');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.family,args.arm,args.position)
