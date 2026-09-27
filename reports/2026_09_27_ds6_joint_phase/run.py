"""All-track CFO with candidate-pair phase factors; bounded geographic screen."""
import hashlib
import importlib.util
import json
import argparse
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('geo',ROOT/'2026_09_27_ds6_geographic_phase/run.py')
geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def coupled(a,b,factor):
    """Joint candidate evidence, each track counted exactly once."""
    return logsumexp(a[:,None,None]+b[None,:,None]+factor,axis=(0,1))


def freeze():
    source=ROOT/'2026_09_27_ds6_expanded_association/inputs.json'
    inputs=json.loads(source.read_text());shortlists={};provenance={}
    for s in inputs['scans']:
        if not s['groups']:continue
        p=ROOT/'2026_09_27_ds6_full_cfo'/f"{s['session_id']}.json"
        r=json.loads(p.read_text());assert r['complete']
        # Copy the exact candidate proposals: subsequent execution does not import
        # or depend on the unpublished full-CFO implementation.
        shortlists[s['session_id']]=r['shortlists']
        provenance[s['session_id']]=dict(source_sha256=sha(p),minimum_anchor_top8_mass=r['minimum_anchor_top8_mass'],method='Union of top8 training candidates over center and four +/-12km anchors and quarter-second timing grid')
    protocol=dict(grid=json.loads((ROOT/'2026_09_27_ds6_geographic_phase/protocol.json').read_text()),inputs_sha256=sha(source),shortlists=shortlists,proposal_provenance=provenance,model='All track CFO once; replace independent pair sums with coupled phase factor; shared baseline across scans; separate scan timing',limitations='Approximate frozen candidate proposals; both RX track likelihoods treated as independent; no reference read until scoring')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run():
    protocol=json.loads((HERE/'protocol.json').read_text());grid=protocol['grid']
    path=ROOT/'2026_09_27_ds6_expanded_association/inputs.json';assert sha(path)==protocol['inputs_sha256'];inputs=json.loads(path.read_text())
    taus=np.array(grid['timing_s']);vectors=np.array([b['enu_m'] for b in grid['baselines']]);banks=[]
    for s in inputs['scans']:
        if not s['groups']:continue
        path=ROOT/s['plan_path'];assert sha(path)==s['plan_sha256'];plan=json.loads(path.read_text());cat=geo.pair.u.load_catalogue(plan)
        tracks={};changes={}
        for t in plan['tracks']:
            mask=np.array(t['training_mask'],bool)
            if mask.sum()<2 or (~mask).sum()<1:continue
            ids=np.array(protocol['shortlists'][s['session_id']][t['track_id']]);p,v,valid=geo.propagate_candidate_states(cat,ids,plan['start_utc_ns'],np.array(t['times_s']),taus)
            assert np.array_equal(ids,valid)
            tracks[t['track_id']]=dict(t=t,p=p,v=v,mask=mask,ids=ids)
        used=[]
        for g in s['groups']:
            used+=g['track_ids']
            for tid in g['track_ids']:
                p,v,ids=geo.propagate_candidate_states(cat,tracks[tid]['ids'],plan['start_utc_ns'],np.array([o['time_s'] for o in g['observations']]),taus)
                assert np.array_equal(ids,tracks[tid]['ids']);changes[tid]=p
        assert len(used)==len(set(used)),'Overlapping factors require a different graph integration'
        banks.append(dict(scan=s,tracks=tracks,changes=changes,catalogue_size=len(cat.names)))
    results=[]
    for point in grid['points']:
        lat0,lon0=grid['center_from_cfo'];lat=lat0+np.degrees(point['north_km']/6371.0088);lon=lon0+np.degrees(point['east_km']/6371.0088)/np.cos(np.radians(lat0));rec=geo.geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rot=np.stack([[-np.sin(lo),np.cos(lo),0],[-np.sin(la)*np.cos(lo),-np.sin(la)*np.sin(lo),np.cos(la)],up],axis=-1);scans=[]
        for bank in banks:
            scores={};delta={};ct=np.zeros(len(taus));cj=ct.copy()
            for tid,b in bank['tracks'].items():
                d=b['p']-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);pred=-geo.REFERENCE_RF_HZ/geo.LIGHT_KM_S*np.sum(d*b['v'],axis=-1);a,j=geo.pair.u.robust_scores(np.array(b['t']['measured_hz'])-pred,b['mask'],sigma=100.);visible=np.any((d@up)[...,b['mask']]>=0,axis=-1);a=np.where(visible,a,-np.inf)-np.log(bank['catalogue_size']);j=np.where(visible,j,-np.inf)-np.log(bank['catalogue_size']);scores[tid]=(a,j);ct+=logsumexp(a,axis=0);cj+=logsumexp(j,axis=0)
                if tid in bank['changes']:
                    d=bank['changes'][tid]-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);delta[tid]=(d[:,:,1]-d[:,:,0])@rot
            tr=np.broadcast_to(ct,(len(vectors),len(taus))).copy();jo=np.broadcast_to(cj,tr.shape).copy()
            for g in bank['scan']['groups']:
                left,right=g['track_ids'];scale=2*np.pi*bank['tracks'][left]['t']['rf_hz']/299792458.
                for ti in range(len(taus)):
                    f=geo.baseline.previous.factor(g['correlation'],scale*((delta[right][:,ti][None,:,:]-delta[left][:,ti][:,None,:])@vectors.T),.1)
                    for out,which in [(tr,0),(jo,1)]:
                        a=scores[left][which][:,ti];b=scores[right][which][:,ti]
                        out[:,ti]+=coupled(a,b,f)-logsumexp(a)-logsumexp(b)
            scans.append(dict(session_id=bank['scan']['session_id'],tracks=len(bank['tracks']),observations=sum(len(b['t']['times_s']) for b in bank['tracks'].values()),train=tr.tolist(),joint=jo.tolist(),cfo_train=ct.tolist(),cfo_joint=cj.tolist()))
        result=dict(point=point,latitude_deg=lat,longitude_deg=lon,scans=scans,scores=geo.combine(scans));results.append(result);print(point['index'],result['scores']['cfo_only'],result['scores']['phase'],flush=True)
    (HERE/'results.json').write_text(json.dumps(dict(complete=True,protocol_sha256=sha(HERE/'protocol.json'),points=results),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--quarter',action='store_true');args=parser.parse_args()
    if args.quarter:
        original=HERE/'protocol.json';p=json.loads(original.read_text());p['parent_protocol_sha256']=sha(original);p['grid']['timing_s']=np.arange(-5.,5.001,.25).tolist();p['timing_audit']='Same nine locations and observations; refine timing only before interpreting strong geographic scores'
        HERE=HERE/'quarter';HERE.mkdir(exist_ok=True)
        if (HERE/'protocol.json').exists():assert json.loads((HERE/'protocol.json').read_text())==p
        else:(HERE/'protocol.json').write_text(json.dumps(p,indent=2)+'\n')
        run()
    else:freeze() if args.freeze else run()
