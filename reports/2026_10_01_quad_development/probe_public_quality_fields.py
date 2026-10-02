"""Read pinned public projection source and verify reader provenance; no data load."""
import json
from pathlib import Path
import subprocess
from run_window import prepare_window
from check_receiver_curvature import save
from screen_seed_prefix import digest

HERE=Path(__file__).resolve().parent
RUNTIME='/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python'


def main():
    provenance=HERE.parent/'2026_10_01_localization_goal/held-out/reader-provenance.json'
    code="""
import importlib,inspect,hashlib,json,pathlib,sys
expected=json.loads(pathlib.Path(sys.argv[1]).read_text())['module_sha256']
actual={}
for name,value in expected.items():
    module=importlib.import_module(name)
    actual[name]='sha256:'+hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()
    assert actual[name]==value,name
from leo.application.scanner_trajectory import project_scanner_candidates
module=importlib.import_module(project_scanner_candidates.__module__)
print(json.dumps(dict(module_sha256=actual,projection_module_path=module.__file__,projection_module_sha256='sha256:'+hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest(),projection_source=inspect.getsource(project_scanner_candidates))))
"""
    completed=subprocess.run(['sudo','-n','-u','leo',RUNTIME,'-c',code,str(provenance)],capture_output=True,text=True,check=True,timeout=30)
    result=json.loads(completed.stdout)
    result.update(runtime=RUNTIME,inputs={str(provenance):digest(provenance)},sources={str(Path(__file__).resolve()):digest(__file__)},
        qualification='Read-only source inspection, not a quality-data export or calibration; no RF/IQ read.')
    save(HERE/'public-quality-source-v1.json',result)


if __name__=='__main__':main()
