#!/usr/bin/env python3
"""Feasibility benchmark only: one frozen cell and first TRAIN scan."""
import hashlib, importlib.util, json, sys, time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).parents[2]; HERE=Path(__file__).parent
SEARCH=ROOT/"reports/2026_09_23_long_training_search/search.py"
LOADER=ROOT/"reports/2026_09_23_long_training_fast_score/loader.py"
CONE=ROOT/"reports/2026_09_23_train_pointing_cone/run.py"
CACHE=Path("/tmp/leo-long-training-cache-full8h")
META=Path("/tmp/leo-train-rx-metadata.json")
LOCATION=(37.6959286096817,-122.65516229557144)
WIDTHS=(10,15,20,30)

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); sys.modules[name]=m; s.loader.exec_module(m); return m
def digest(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()

def prepare_track(search, cone, track, receiver, up):
    delta=track["position"]-receiver; distance=np.linalg.norm(delta,axis=-1)
    prediction=-search.REFERENCE_RF_HZ/search.LIGHT_KM_S*np.sum(delta*track["velocity"],axis=-1)/distance
    mask=track["training_mask"]; residual=track["measured_hz"][None,:]-prediction
    offsets=np.mean(residual[:,mask],axis=1); errors=residual-offsets[:,None]
    rms=np.sqrt(np.mean(errors[:,mask]**2,axis=1))
    visible=np.max(np.sum(delta*up,axis=-1)/distance,axis=1)>=0
    keep=visible & (rms<800.0)
    dirs=cone.enu_directions(search,*LOCATION,receiver,track["position"][:,mask,:].reshape(-1,3)).reshape(len(rms),-1,3)
    return {"keep":keep,"cost":np.minimum((rms/800.)**2,1.),"dirs":dirs,"errors":errors,
            "mask":mask,"weight":track["weight_s"],"track_id":track["track_id"]}

def exact(cone, tracks, receiver_ids, batch=256):
    orientations=cone.orientation_grid(15); axes=cone.axes_batched(orientations)
    best={(mapping,width):(-1.,None) for mapping in ((0,1),(1,0)) for width in WIDTHS}
    evaluated=0; started=time.monotonic()
    for start in range(0,len(orientations),batch):
        stop=min(start+batch,len(orientations)); gains={(m,w):np.zeros(stop-start) for m in ((0,1),(1,0)) for w in WIDTHS}
        for ti,t in enumerate(tracks):
            dirs=t["dirs"][t["keep"]]; costs=t["cost"][t["keep"]]
            if not len(dirs): continue
            for mapping in ((0,1),(1,0)):
                axis=axes[start:stop,mapping[receiver_ids[ti]]]
                cosine=np.einsum("oc,skc->osk",axis,dirs,optimize=True).min(axis=2)
                for width in WIDTHS:
                    compatible=cosine>=np.cos(np.radians(width))
                    improvement=np.max(np.where(compatible,1-costs[None,:],0.),axis=1)
                    gains[(mapping,width)]+=t["weight"]*improvement
        for key,value in gains.items():
            i=int(np.argmax(value)); candidate=(float(value[i]),start+i)
            if candidate[0]>best[key][0]: best[key]=candidate
        evaluated += stop-start
    return orientations,axes,best,evaluated,time.monotonic()-started

def main():
    begun=time.monotonic(); search=load(SEARCH,"joint_search"); loader=load(LOADER,"joint_loader"); cone=load(CONE,"joint_cone")
    manifest=json.loads((ROOT/"reports/2026_09_23_long_training_cache_full8h/manifest.json").read_text())
    sid=manifest["source_group"]["session_ids"][0]; session=loader.load_session(search,CACHE/sid,sid)
    metadata=json.loads(META.read_text())["sessions"]; md=next(s for s in metadata if s["session_id"]==sid); labels={t["track_id"]:int(t["receiver_id"]) for t in md["tracks"]}
    receiver,up=search.receiver_ecef(*LOCATION); tracks=[prepare_track(search,cone,t,receiver,up) for t in session["prepared"]]
    receiver_ids=np.asarray([labels[t["track_id"]] for t in tracks]); orientations,axes,best,evaluated,search_s=exact(cone,tracks,receiver_ids)
    total=sum(t["weight"] for t in tracks); scenarios=[]
    for (mapping,width),(gain,oi) in best.items():
        supported=0; held_sq=held_n=0; held_loss=0.; assignments=[]
        for ti,t in enumerate(tracks):
            ix=np.flatnonzero(t["keep"])
            if len(ix):
                axis=axes[oi,mapping[receiver_ids[ti]]]; compatible=np.min(np.einsum("skc,c->sk",t["dirs"][ix],axis),axis=1)>=np.cos(np.radians(width))
                viable=ix[compatible]; winner=viable[np.argmin(t["cost"][viable])] if len(viable) else None
            else: winner=None
            if winner is None: held_loss+=t["weight"]
            else:
                supported+=1; held=t["errors"][winner,~t["mask"]]; held_sq+=float(np.sum(held**2)); held_n+=len(held)
                held_cost=min(float(np.mean(held**2))/800**2,1.); held_loss+=t["weight"]*held_cost
            assignments.append({"track_id":t["track_id"],"candidate_index":None if winner is None else int(winner)})
        scenarios.append({"mapping":list(mapping),"width_deg":width,"orientation":[int(x) for x in orientations[oi]],"training_loss":1-gain/total,"supported_tracks":supported,"unsupported_tracks":len(tracks)-supported,"held_rms_hz_supported":None if not held_n else (held_sq/held_n)**.5,"held_capped_loss_all_tracks":held_loss/total,"assignments":assignments})
    receipt=json.loads((CACHE/sid/"cache_receipt.json").read_text())
    out={"schema":"joint-cone-feasibility-prototype/v1","scientific_result":False,"scope":{"cell":"fixed_cell_1","session_id":sid,"scan_count":1,"cell_count":1},"catalogue_policy":receipt["candidate_policy"],"candidate_count":len(session["candidate_ids"]),"eligible_tracks":len(tracks),"retained_candidate_counts":[int(np.sum(t["keep"])) for t in tracks],"orientation_count":len(orientations),"evaluated_orientations":evaluated,"exact_search_s":search_s,"elapsed_s":time.monotonic()-begun,"scenarios":scenarios,"bindings":{"protocol":digest(HERE/"PROTOCOL.md"),"source":digest(__file__),"receipt":digest(CACHE/sid/"cache_receipt.json"),"cache":digest(CACHE/sid/"state_cache.npz"),"metadata":digest(META)}}
    (HERE/"prototype_results.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")

if __name__=="__main__": main()
