import hashlib, importlib.util, json, sys
from pathlib import Path
HERE=Path(__file__).parent; ROOT=HERE.parents[1]
def digest(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()
run_path=HERE/"run.py"; spec=importlib.util.spec_from_file_location("grid_receipt_run",run_path); run=importlib.util.module_from_spec(spec); sys.modules[spec.name]=run; spec.loader.exec_module(run)
base_path=run.BASE_PATH; base_spec=importlib.util.spec_from_file_location("grid_receipt_base",base_path); base=importlib.util.module_from_spec(base_spec); sys.modules[base_spec.name]=base; base_spec.loader.exec_module(base)
manifests={"first_train":ROOT/"reports/2026_09_23_long_training_cache_full8h/manifest.json","second_train":ROOT/"reports/2026_09_23_long_training_cache_second8h/manifest.json"}
out={"schema":"local-cone-grid-dependency-receipt/v1","inference":digest(HERE/"inference.json"),"protocol":digest(HERE/"PROTOCOL.md"),"run":digest(run_path),"base":digest(base_path),"width":digest(run.WIDTH_PATH),"search":digest(base.SEARCH),"loader":digest(base.LOADER),"cone":digest(base.CONE),"metadata":digest(base.META),"manifests":{k:digest(v) for k,v in manifests.items()}}
(HERE/"dependency_receipt.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
