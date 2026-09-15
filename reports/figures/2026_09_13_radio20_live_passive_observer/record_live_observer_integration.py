"""Freeze host integration evidence; no radio contact or RF collection."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from review_live_observer import review,check_rotation

BASE=Path(__file__).parent
FW=Path('/home/mouse9911/gits/plutosdr-fw-radio20-tracking')
OUT=BASE/'passive-observer-live-host-v1'


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    result={'scope':'live_observer_host_integration','new_rf_samples':0,'native_hardware_executed':False,
            'native_tracking_qualified':False,'fw_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=FW,text=True).strip(),
            'binary':{'path':str(BASE/'glrt-cpu-live-probe-v12'),'sha256':digest(BASE/'glrt-cpu-live-probe-v12')},
            'compiler_flags':['-std=c99','-O3','-mcpu=cortex-a9','-mfpu=neon','-Wall','-Wextra','-Werror','-pthread'],
            'sources':{},'cases':{},'rotation_scalar_checks':check_rotation()}
    for path in sorted((FW/'tools').glob('glrt_*')):
        if path.suffix in ('.c','.h','.inc'): result['sources'][str(path.relative_to(FW))]=digest(path)
    junit=BASE/'passive-observer-live-tests-v2.xml'
    shutil.copyfile(junit,OUT/junit.name)
    suite=ET.parse(junit).getroot().find('testsuite')
    result['tests']={k:suite.attrib[k] for k in ('tests','failures','errors','skipped','time')}
    selected={'native30':'test_advancing_capture_worker_0','native60':'test_advancing_capture_worker_1',
              'reacquire30':'test_clean_native_loss_reacqui0','reacquire60':'test_clean_native_loss_reacqui1'}
    for label,name in selected.items():
        source=Path('/tmp/pytest-of-mouse9911/pytest-9')/name
        destination=OUT/label;destination.mkdir()
        for filename in ('observer.jsonl','observer.iq.ci16','worker.jsonl','capture.txt'):
            shutil.copyfile(source/filename,destination/filename)
        reviewed=review(destination)
        reviewed['artifacts']={p.name:digest(p) for p in destination.iterdir()}
        result['cases'][label]=reviewed
    for filename in ('review_live_observer.py','record_live_observer_integration.py'):
        shutil.copyfile(BASE/filename,OUT/filename)
    result['live_attempt']=json.loads((BASE/'cpu-live60-passive-observer-v1/operator.json').read_text())
    assert result['live_attempt']['status']=='admission_refused' and result['live_attempt']['rf_samples_collected']==0
    result['status']='host_pass_arm_build_pass_live_admission_refused'
    (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(OUT),'tests':result['tests'],'fw_commit':result['fw_commit'],
                      'moments_and_dense_fits_checked':sum(c['moments_and_dense_fits_checked'] for c in result['cases'].values())}))


if __name__=='__main__': main()
