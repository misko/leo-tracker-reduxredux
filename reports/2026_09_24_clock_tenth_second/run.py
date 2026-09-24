#!/usr/bin/env python3
import hashlib, importlib.util, json, sys, time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).parents[2]; HERE=Path(__file__).parent
PARENT=ROOT/"reports/2026_09_24_shared_clock_grid/inference.json"; PARENT_SEAL=ROOT/"reports/2026_09_24_shared_clock_grid/inference.sha256"; ENGINE=ROOT/"reports/2026_09_24_shared_clock_grid/run.py"
TAUS=np.arange(-15,-4,dtype=int)/10
def digest(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); sys.modules[name]=m; s.loader.exec_module(m); return m
def main():
 raw=PARENT.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=PARENT_SEAL.read_text().strip(): raise ValueError("parent seal mismatch")
 parent=json.loads(raw); prior=next(r for r in parent["rows"] if r["point_id"]=="p0007"); engine=load(ENGINE,"tenth_clock_engine"); begun=time.monotonic(); model=engine.Engine(); train,held,assign=model.profile(prior["latitude_deg"],prior["longitude_deg"],TAUS,True,True); old=int(np.flatnonzero(np.isclose(TAUS,-1))[0])
 if abs(float(train[old])-prior["clock_training_loss"])>1e-12 or abs(float(held[old])-prior["clock_held_loss"])>1e-12: raise AssertionError("minus-one parity failed")
 best=engine.select_tau(train,TAUS); out={"schema":"clock-tenth-second/v1","complete":True,"point_id":"p0007","latitude_deg":prior["latitude_deg"],"longitude_deg":prior["longitude_deg"],"tau_s":[float(x) for x in TAUS],"training_capped_loss":[float(x) for x in train],"held_capped_loss":[float(x) for x in held],"selected_tau_s":float(TAUS[best]),"selected_training_capped_loss":float(train[best]),"selected_held_capped_loss":float(held[best]),"assignments":assign[best],"elapsed_s":time.monotonic()-begun,"truth_used":False,"held_used_for_selection":False,"bindings":{"protocol":digest(HERE/"PROTOCOL.md"),"source":digest(__file__),"engine":digest(ENGINE),"parent":digest(PARENT)}}; path=HERE/"results.json"; path.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); (HERE/"results.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest()+"\n")
if __name__=="__main__": main()
