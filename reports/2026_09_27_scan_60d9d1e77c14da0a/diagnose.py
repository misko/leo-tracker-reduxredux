"""Local identifiability diagnostic; fixed Sacramento shortlist, training-selected grid."""
import json,sys,time
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
import run as source

HERE=Path(__file__).resolve().parent


def main():
    start=time.monotonic();old=json.loads((HERE/'results.json').read_text())
    short=json.loads((HERE/'shortlist.json').read_text())
    store=source.ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        raw=store.load(source.SID)
        p=source.prepare_adaptive_tle_position_inputs(source.SID,inputs=store,archive=source.TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    assert old['evidence_sha256']==p.evidence_sha256
    import leo.operations.adaptive_tle_position_inputs as inputs
    trajectory=inputs.reconstruct_persistent_hop_trajectories(inputs.project_scanner_candidates(raw),
        config=inputs.PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
    graphs=dict(inputs._graphs(trajectory))
    center=old['sites']['sacramento'];point=source.point_factory(center['latitude_deg'],center['longitude_deg'])
    offsets=[(float(e),float(n)) for e in (-10,-5,0,5,10) for n in (-10,-5,0,5,10)]
    points=[point(e,n) for e,n in offsets]
    gt=old['sites']['reference'];points.append(source.point_factory(gt['latitude_deg'],gt['longitude_deg'])(0,0))
    train=np.zeros((len(points),len(p.tracks)));predict=train.copy();rows=[]
    delta=np.arange(-1200,1201)/10;cal=json.loads(source.CALPATH.read_text())
    lookup={str(c):i for i,c in enumerate(p.catalogue.satellite_numbers)};epochs=p.catalogue.element_epoch_utc_ns();cache={}
    frozen={t['track_id']:next(iter(t['probabilities'])) for t in old['results']['sacramento']['baseline_frozen']['tracks']}
    for k,t in enumerate(p.tracks):
        mask=np.asarray(t.training_mask,bool);tid=t.track_id
        ids=sorted({r['candidate_id'] for r in short['candidates']['sacramento'][tid]}|{frozen[tid]},key=int)
        lp={}
        for cid in ids:
            age=(p.start_utc_ns-epochs[lookup[cid]])/3.6e12;key=source.age_bin(cal['model'],age)['lower_h']
            if key not in cache:cache[key]=source.discrete_weights(cal['model'],age,delta)[0]
            lp[cid]=cache[key]
        banks,_=source.build_prediction_banks(p.catalogue,[lookup[c] for c in ids],p.start_utc_ns,[t],taus_s=delta)
        diag=None
        for j,pt in enumerate(points):
            zs=[];js=[];details=[]
            for b in source.RegionalTrackPredictionEvaluator(banks,lambda e,n,pt=pt:pt,taus_s=delta)(0,0):
                for i,c in enumerate(b.candidate_ids):
                    cid=str(c)
                    if not b.visible[i]:continue
                    res=b.measured_hz[None,:]-b.predictions_hz[i]
                    tr=source.SOFT.block_average(t.times_s,res,mask);te=source.SOFT.block_average(t.times_s,res,~mask)
                    f=source.SOFT.profiles(tr,te,100.);post=lp[cid]+f['train'];z=logsumexp(post)
                    zs.append(z);js.append(logsumexp(post+f['predict']))
                    details.append((cid,post,float(z),int(np.argmax(post)),tr,te))
            train[j,k]=logsumexp(zs)-np.log(len(zs));predict[j,k]=logsumexp(js)-logsumexp(zs)
            if j==12:
                d=max(details,key=lambda d:d[2]);cid,post,z,imax,tr,te=d
                prob=float(np.exp(z-logsumexp(zs)));tau=float(delta[imax]);bhat=float(tr[imax].mean())
                rms=float(np.sqrt(np.mean((te[imax]-bhat)**2)))
                diag={'map_id':cid,'map_probability':prob,'map_tau_s':tau,'test_rms_at_training_map_hz':rms}
        obs=graphs[tid].observations
        rows.append({'track_id':tid,'receivers':sorted({o.stream_id for o in obs}),
            'observations':len(t.times_s),'span_s':float(np.ptp(t.times_s)),
            'occupied_seconds':len(np.unique(np.floor(t.times_s))),
            'train_blocks':len(np.unique(np.floor(t.times_s[mask]))),
            'test_blocks':len(np.unique(np.floor(t.times_s[~mask]))),
            'shared_train_test_second_bins':len(set(np.floor(t.times_s[mask]))&set(np.floor(t.times_s[~mask]))),
            **diag})
        if k%10==0:print('TRACK',k+1,'/',len(p.tracks),'elapsed',round(time.monotonic()-start,1),flush=True)
    total=sum(r['test_blocks'] for r in rows);score=-predict.sum(axis=1)/total
    selected=int(np.argmax(train[:-1].sum(axis=1)))
    # Ground truth is a diagnostic and never enters the grid selection.
    coords=source.load('diag_coordinates',source.REPORTS/'2026_09_26_joint_location_prototype/run_prototype.py').coordinates
    grid=[]
    for j,(e,n) in enumerate(offsets):
        lat,lon=coords(center['latitude_deg'],center['longitude_deg'],e,n)
        lat0,lon0,lat1,lon1=np.deg2rad([gt['latitude_deg'],gt['longitude_deg'],lat,lon])
        error=2*6371.0088*np.arcsin(np.sqrt(np.sin((lat1-lat0)/2)**2+np.cos(lat0)*np.cos(lat1)*np.sin((lon1-lon0)/2)**2))
        grid.append({'east_km':e,'north_km':n,'latitude_deg':lat,'longitude_deg':lon,'error_km':error,
            'training_log_evidence':float(train[j].sum()),'predictive_nll':float(score[j])})
    partitions={}
    for rx in ('rx-0','rx-1'):
        ix=[i for i,r in enumerate(rows) if r['receivers']==[rx]]
        if ix:
            best=int(np.argmax(train[:-1,ix].sum(axis=1)));den=sum(rows[i]['test_blocks'] for i in ix)
            partitions[rx]={'tracks':len(ix),'selected':grid[best],
                'truth_nll_same_sac_candidates':float(-predict[-1,ix].sum()/den),
                'sac_nll':float(-predict[12,ix].sum()/den)}
    original={s:{t['track_id']:t for t in old['results'][s]['soft']['tracks']} for s in old['sites']}
    differences=np.array([original['reference'][t.track_id]['predictive_log_score']-original['sacramento'][t.track_id]['predictive_log_score'] for t in p.tracks])
    for k,r in enumerate(rows):r['truth_minus_sac_logscore_independent_candidates']=float(differences[k])
    rng=np.random.default_rng(20260927)
    bootstrap=np.array([differences[ix].sum()/sum(rows[i]['test_blocks'] for i in ix)
        for ix in rng.integers(0,len(rows),size=(3000,len(rows)))])
    summary={'session_id':source.SID,'evidence_sha256':p.evidence_sha256,
        'protocol':'Diagnostic 5x5 grid +/-10km around Sacramento only, same Sacramento training shortlist+frozen IDs throughout; zero clock; timing +/-120 at 0.1s; training evidence selects position; truth excluded from grid selection. Conditional shortlist search, not full-catalogue location search.',
        'geometry_radio_id':raw.radio_id,'timing_bracket_s':raw.timing.first_sample_bracket_width_ns/1e9,
        'observations':sum(r['observations'] for r in rows),'heldout_blocks':total,
        'shared_train_test_second_bins':sum(r['shared_train_test_second_bins'] for r in rows),
        'grid':grid,'training_selected':grid[selected],'truth_nll_same_sac_candidates':float(score[-1]),
        'sac_parity_difference':float(score[12]-old['summary']['soft']['scores']['sacramento']),
        'receivers':partitions,'tracks':rows,
        'track_bootstrap_truth_minus_sac_logscore_95':np.quantile(bootstrap,[.025,.975]).tolist(),
        'track_bootstrap_truth_wins_fraction':float(np.mean(bootstrap>0)),
        'bootstrap_warning':'Tracks can be correlated; descriptive robustness only.',
        'elapsed_s':time.monotonic()-start}
    assert abs(summary['sac_parity_difference'])<1e-8
    source.atomic(HERE/'diagnosis.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('tracks','grid')},indent=2))


if __name__=='__main__':main()
