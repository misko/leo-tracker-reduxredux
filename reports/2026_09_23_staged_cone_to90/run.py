#!/usr/bin/env python3
import hashlib, importlib.util, json, sys
from pathlib import Path

ROOT=Path(__file__).parents[2]; HERE=Path(__file__).parent
SOURCE=ROOT/"reports/2026_09_23_staged_cone_width_sweep/run.py"
WIDTHS=(10.0,20.0,25.0,30.0,40.0,50.0,60.0,70.0,80.0,90.0)

def digest(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module); return module

def main():
 sweep=load(SOURCE,"staged_to90_source"); sweep.HERE=HERE; sweep.WIDTHS=WIDTHS; sweep.main()
 path=HERE/"results.json"; result=json.loads(path.read_text()); result["schema"]="staged-cone-to90/v1"; result["bindings"]["wrapper"]=digest(__file__); result["bindings"]["width_sweep_source"]=digest(SOURCE)
 path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); (HERE/"results.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest()+"\n")
if __name__=="__main__": main()
