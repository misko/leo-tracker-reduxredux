"""Validate a completed use build without repeating completed PGO training."""
import json,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
m=runpy.run_path(str(ROOT/'run_training.py'))
a=m['a'];build=ROOT/'builds/use'
profiles=json.loads((ROOT/'profile-retrieval.json').read_text())
assert a.sha(ROOT/'profile-data.tar.gz')==profiles['archive_sha256']
receipt=json.loads((build/'build-receipt.json').read_text())
results=[]
for unit in sorted(build.glob('test_*_arm')):
    assert a.sha(unit)==receipt['binaries'][unit.name]
    destination='/tmp/wave8-validation-unit'
    a.upload(unit,destination)
    stdout=a.remote('chmod +x '+destination+' && '+destination,timeout=120)
    results.append({'binary':unit.name,'sha256':a.sha(unit),'stdout':stdout})
(ROOT/'arm-units-use.json').write_text(json.dumps(results,indent=2)+'\n')
a.remote('rm -f /tmp/wave8-validation-unit')
m['evaluate']('use',ROOT.parent/'2026_09_29_arm_wave6_pgo/heldout32-reference','arm-heldout32')
m['run']([sys.executable,str(ROOT.parent/'2026_09_29_arm_rate_coarse_gate/audit.py'),'--cohort',str(ROOT/'arm-heldout32')])
