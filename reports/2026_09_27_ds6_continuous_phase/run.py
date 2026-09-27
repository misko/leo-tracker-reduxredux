"""Continuous shared position and scan clocks with joint CFO/phase factors."""
import argparse
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('joint',ROOT/'2026_09_27_ds6_joint_phase/run.py');joint=importlib.util.module_from_spec(spec);spec.loader.exec_module(joint);geo=joint.geo


def freeze():
    source=ROOT/'2026_09_27_ds6_joint_phase/protocol.json'
    grid=ROOT/'2026_09_27_ds6_joint_phase/quarter/results.json'
    p=json.loads(source.read_text());r=json.loads(grid.read_text());assert r['complete']
    starts=[]
    for index in [2,4]:
        row=r['points'][index];starts.append([row['point']['east_km'],row['point']['north_km']]+[-5+.25*int(np.argmax(s['cfo_train'])) for s in row['scans']])
    out=dict(parent_sha256=joint.sha(source),grid_sha256=joint.sha(grid),starts=starts,bounds=[[-12.,12.],[-12.,12.]]+[[-5.,5.]]*3,method='L-BFGS-B, train only, maxiter60 maxfun650; shared baseline marginalized; continuous scan timing profiled equally in both arms',interpolation_step_s=.25,arms=['cfo_only','phase'],reference_policy='No operator reference loaded during fit',scope='Three evaluable scans, inherited approximate proposals, two starts; local conditional fit')
    with (HERE/'protocol.json').open('x') as f:json.dump(out,f,indent=2)


class Model:
    def __init__(self):
        self.protocol=json.loads((HERE/'protocol.json').read_text());path=ROOT/'2026_09_27_ds6_joint_phase/protocol.json';assert joint.sha(path)==self.protocol['parent_sha256'];p=json.loads(path.read_text());self.center=p['grid']['center_from_cfo'];self.vectors=np.array([b['enu_m'] for b in p['grid']['baselines']]);self.banks=[]
        path=ROOT/'2026_09_27_ds6_expanded_association/inputs.json';assert joint.sha(path)==p['inputs_sha256']
        for scan in json.loads(path.read_text())['scans']:
            if not scan['groups']:continue
            path=ROOT/scan['plan_path'];assert joint.sha(path)==scan['plan_sha256'];plan=json.loads(path.read_text());cat=geo.pair.u.load_catalogue(plan);tracks={}
            phase_times={tid:np.array([o['time_s'] for o in g['observations']]) for g in scan['groups'] for tid in g['track_ids']}
            for t in plan['tracks']:
                mask=np.array(t['training_mask'],bool)
                if mask.sum()<2 or (~mask).sum()<1:continue
                tid=t['track_id'];ids=np.array(p['shortlists'][scan['session_id']][tid]);times=np.r_[t['times_s'],phase_times.get(tid,[])];pos,vel,valid=geo.propagate_candidate_states(cat,ids,plan['start_utc_ns'],times,np.arange(-5,5.001,.25));assert np.array_equal(ids,valid)
                tracks[tid]=dict(t=t,mask=mask,p=pos,v=vel,ids=ids,times=times)
            self.banks.append(dict(scan=scan,tracks=tracks,cat=cat,start=plan['start_utc_ns']))

    def coordinates(self,x):
        return [self.center[0]+np.degrees(x[1]/6371.0088),self.center[1]+np.degrees(x[0]/6371.0088)/np.cos(np.radians(self.center[0]))]

    def evaluate(self,x,arm,exact=False):
        lat,lon=self.coordinates(x);rec=geo.geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rot=np.stack([[-np.sin(lo),np.cos(lo),0],[-np.sin(la)*np.cos(lo),-np.sin(la)*np.sin(lo),np.cos(la)],up],axis=-1);tr=np.zeros(len(self.vectors));jo=tr.copy();predictions=[]
        for si,bank in enumerate(self.banks):
            tau=x[si+2];q=(tau+5)*4;loi=min(39,max(0,int(np.floor(q))));w=q-loi;scores={};changes={}
            for tid,b in bank['tracks'].items():
                if exact:
                    p,v,valid=geo.propagate_candidate_states(bank['cat'],b['ids'],bank['start'],b['times'],np.array([tau]));assert np.array_equal(valid,b['ids']);p=p[:,0];v=v[:,0]
                else:p=b['p'][:,loi]*(1-w)+b['p'][:,loi+1]*w;v=b['v'][:,loi]*(1-w)+b['v'][:,loi+1]*w
                d=p-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);n=len(b['mask']);pred=-geo.REFERENCE_RF_HZ/geo.LIGHT_KM_S*np.sum(d[:,:n]*v[:,:n],axis=-1);predictions.append(pred);a,j=geo.pair.u.robust_scores(np.array(b['t']['measured_hz'])-pred,b['mask'],sigma=100.);visible=np.any((d[:,:n]@up)[:,b['mask']]>=0,axis=-1);a=np.where(visible,a,-np.inf)-np.log(len(bank['cat'].names));j=np.where(visible,j,-np.inf)-np.log(len(bank['cat'].names));scores[tid]=(a,j);tr+=logsumexp(a);jo+=logsumexp(j)
                if d.shape[1]>n:changes[tid]=(d[:,n+1]-d[:,n])@rot
            if arm=='phase':
                for g in bank['scan']['groups']:
                    left,right=g['track_ids'];scale=2*np.pi*bank['tracks'][left]['t']['rf_hz']/299792458.;f=geo.baseline.previous.factor(g['correlation'],scale*((changes[right][None,:,:]-changes[left][:,None,:])@self.vectors.T),.1)
                    for out,which in [(tr,0),(jo,1)]:
                        a,b=scores[left][which],scores[right][which];out+=joint.coupled(a,b,f)-logsumexp(a)-logsumexp(b)
        train=logsumexp(tr)-np.log(len(tr));return dict(train=float(train),held=float(logsumexp(jo)-np.log(len(jo))-train),baseline_posterior=np.exp(tr-logsumexp(tr)).tolist(),predictions=predictions)


def run(arm):
    start=time.monotonic();model=Model();runs=[]
    for x in model.protocol['starts']:
        fit=minimize(lambda x:-model.evaluate(x,arm)['train'],np.array(x),method='L-BFGS-B',bounds=model.protocol['bounds'],options=dict(maxiter=60,maxfun=650,ftol=1e-11,gtol=1e-5,eps=1e-4));r=model.evaluate(fit.x,arm);r.pop('predictions');runs.append(dict(x=fit.x.tolist(),coordinates=model.coordinates(fit.x),success=bool(fit.success),message=str(fit.message),nfev=fit.nfev,initial=x,**r));print(arm,runs[-1],flush=True)
    best=max(runs,key=lambda r:r['train']);approx=model.evaluate(best['x'],arm);exact=model.evaluate(best['x'],arm,True);err=max(float(np.max(abs(a-b))) for a,b in zip(approx.pop('predictions'),exact.pop('predictions')))
    out=dict(complete=True,arm=arm,protocol_sha256=joint.sha(HERE/'protocol.json'),runs=runs,best=best,exact=exact,maximum_interpolation_error_hz=err,bound_hit=any(min(abs(v-a),abs(v-b))<.001 for v,(a,b) in zip(best['x'],model.protocol['bounds'])),elapsed_s=time.monotonic()-start)
    (HERE/f'{arm}.json').write_text(json.dumps(out,indent=2)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');ap.add_argument('--arm',choices=['cfo_only','phase']);args=ap.parse_args();freeze() if args.freeze else run(args.arm)
