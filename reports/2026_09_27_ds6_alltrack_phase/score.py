"""All-track composite CFO score with one shared scan time and joined phase."""
import sys,json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_orbit_phase'))
from run import cfo_evidence,phase_evidence

def shared_time_score(track_log_evidence):
    a=np.asarray(track_log_evidence)
    return float(logsumexp(a.sum(axis=0))-np.log(a.shape[1]))

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--stage',type=int,default=0,choices=[0,1,2,3]);args=parser.parse_args()
    output=HERE/'results.json' if args.stage==0 else HERE/f'refine-{args.stage}.json'
    if args.stage:
        previous=json.loads((HERE/('results.json' if args.stage==1 else f'refine-{args.stage-1}.json')).read_text());assert previous['complete']
        centers={(previous[k]['latitude'],previous[k]['longitude']) for k in ['best_cfo','best_joint']}
        coordinates=sorted({(float(lat),float(lon)) for a,b in centers for lat in np.linspace(a-.2/4**(args.stage-1),a+.2/4**(args.stage-1),9) for lon in np.linspace(b-.25/4**(args.stage-1),b+.25/4**(args.stage-1),9)})
    else:coordinates=[(float(lat),float(lon)) for lat in np.linspace(36.8,40.,9) for lon in np.linspace(-124.,-120.,9)]
    inp=json.loads((HERE/'inputs.json').read_text());tracks=inp['tracks'];taus=np.arange(-5.,6.)
    # Use one sample per whole dwell, retaining its frozen assignment.
    for t in tracks:
        visits=np.array(t['visits']);unique=np.unique(visits);times=np.array(t['times_s']);values=np.array(t['measured_hz']);mask=np.array(t['training_mask'])
        t['t']=np.array([times[visits==v].mean() for v in unique]);t['y']=np.array([values[visits==v].mean() for v in unique]);t['mask']=np.array([mask[visits==v][0] for v in unique]);assert all(np.all(mask[visits==v]==mask[visits==v][0]) for v in unique)
    tracks=[t for t in tracks if t['mask'].sum()>=2 and (~t['mask']).sum()>=1]
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));snap=archive.select_latest_before(inp['start_utc_ns']-505_000_000_000);assert snap.digest==inp['snapshot_digest'];payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    nodes=np.arange(np.floor(min(t['t'].min() for t in tracks))-6,np.ceil(max(t['t'].max() for t in tracks))+7)
    pos,vel,ids=propagate_candidate_states(cat,np.arange(len(cat.satellite_numbers)),inp['start_utc_ns'],nodes,np.array([0.]));pos=pos[:,0];vel=vel[:,0]
    phase_rows=json.loads((ROOT/'2026_09_27_latest_ten_phase'/f"{inp['session_id']}.json").read_text())['rows'];pairs=[]
    for pair in inp['recurring_rx0_pairs']:
        if not all(tid in {t['track_id'] for t in tracks} for tid in pair['track_ids']):continue
        obs=[]
        for visit in pair['visits']:
            rr=[r for r in phase_rows if r['visit']==visit and r['both_qualified']]
            if rr:obs.append(dict(t=float(np.mean([r['time_s'] for r in rr])),y=float(np.angle(np.mean([np.exp(1j*(r['modes'][1]['evaluation']['phase_rad']-r['modes'][0]['evaluation']['phase_rad'])) for r in rr]))),train=rr[0]['partition']=='train'))
        if len(obs)>=4:pairs.append(dict(ids=pair['track_ids'],obs=obs))
    assert len(pairs)==1,'Review factor-graph dependence before adding overlapping pairs'
    def interpolate(a,t):
        query=np.asarray(t)+taus[:,None]-nodes[0];lo=np.floor(query).astype(int);w=query-lo
        return a[:,lo]*(1-w)+a[:,lo+1]*w
    result=[]
    for lat in sorted({a for a,b in coordinates}):
      for lon in sorted(b for a,b in coordinates if a==lat):
        la,ln=np.radians([lat,lon]);receiver=geodetic_to_ecef_km(lat,lon,0);up=np.array([np.cos(la)*np.cos(ln),np.cos(la)*np.sin(ln),np.sin(la)]);east=np.array([-np.sin(ln),np.cos(ln),0.])
        dr=pos-receiver;dist=np.linalg.norm(dr,axis=-1);elevation=np.sum(dr*up,axis=-1)/dist;possible=np.any(elevation>=0,axis=1);active=np.flatnonzero(possible)
        unit=dr[active]/dist[active,:,None];pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel[active],axis=-1);el=elevation[active];projection=unit@east
        bytrack={};scores=[]
        for t in tracks:
            prediction=interpolate(pred,t['t']);visible=np.any(interpolate(el,t['t'])[:,:,t['mask']]>=0,axis=-1)
            residual=t['y'][None,None,:]-prediction;tr=cfo_evidence(residual[:,:,t['mask']]);joint=cfo_evidence(residual)
            tr=np.where(visible,tr,-np.inf);joint=np.where(visible,joint,-np.inf)
            bytrack[t['track_id']]=(tr,joint);scores.append((logsumexp(tr,axis=0)-np.log(len(ids)),logsumexp(joint,axis=0)-np.log(len(ids))))
        trsum=np.sum([r[0] for r in scores],axis=0);jsum=np.sum([r[1] for r in scores],axis=0)
        addtrain=np.zeros(len(taus));addjoint=np.zeros(len(taus));masses=[]
        for pair in pairs:
            a,aj=bytrack[pair['ids'][0]];b,bj=bytrack[pair['ids'][1]];obs=pair['obs'];t=np.array([o['t'] for o in obs]);y=np.array([o['y'] for o in obs]);mask=np.array([o['train'] for o in obs]);q=interpolate(projection,t)
            for ti in range(len(taus)):
                ia=np.argsort(a[:,ti])[-6:];ib=np.argsort(b[:,ti])[-6:];logweights=(a[ia,ti,None]+b[ib,ti][None,:])-(logsumexp(a[:,ti])+logsumexp(b[:,ti]));mass=float(np.exp(logsumexp(logweights)));masses.append(mass)
                g=2*np.pi*.08*11.46e9/299792458.*(q[ib,ti][None,:,:]-q[ia,ti][:,None,:])
                factor=logsumexp(np.stack([phase_evidence(y[mask],sign*g[:,:,mask],np.ones(mask.sum())) for sign in [-1,1]]),axis=0)-np.log(2)
                # Unretained candidate mass has a neutral phase factor; no renormalization inflation.
                addtrain[ti]+=np.logaddexp(logsumexp(logweights+factor),np.log(max(1-mass,1e-300)))
                logjoint=(aj[ia,ti,None]+bj[ib,ti][None,:])-(logsumexp(aj[:,ti])+logsumexp(bj[:,ti]));massjoint=float(np.exp(logsumexp(logjoint)))
                factorjoint=logsumexp(np.stack([phase_evidence(y,sign*g,np.ones(len(y))) for sign in [-1,1]]),axis=0)-np.log(2)
                addjoint[ti]+=np.logaddexp(logsumexp(logjoint+factorjoint),np.log(max(1-massjoint,1e-300)))
        row=dict(latitude=float(lat),longitude=float(lon),cfo_train=float(logsumexp(trsum)-np.log(len(taus))),joint_train=float(logsumexp(trsum+addtrain)-np.log(len(taus))),cfo_held=float(logsumexp(jsum)-logsumexp(trsum)),joint_held=float(logsumexp(jsum+addjoint)-logsumexp(trsum+addtrain)),cfo_map_time_s=float(taus[np.argmax(trsum)]),joint_map_time_s=float(taus[np.argmax(trsum+addtrain)]),minimum_retained_phase_candidate_mass=min(masses));result.append(row)
      print('points',len(result),'tracks',len(tracks),flush=True)
      output.write_text(json.dumps(dict(stage=args.stage,complete=len(result)==len(coordinates),rows=result,tracks=len(tracks),track_dwell_observations=sum(len(t['t']) for t in tracks),phase_pairs=len(pairs),valid_catalogue_candidates=len(ids),best_cfo=max(result,key=lambda r:r['cfo_train']),best_joint=max(result,key=lambda r:r['joint_train'])),indent=2)+'\n')
if __name__=='__main__':main()
