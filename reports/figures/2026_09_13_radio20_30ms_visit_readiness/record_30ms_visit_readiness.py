"""Persist successful 30-MS/s deployment and the bounded visit admission findings."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

BASE=Path(__file__).parent
FW=Path('/home/mouse9911/gits/plutosdr-fw-radio20-tracking')
OUT=Path('/home/mouse9911/gits/leo-radio20-reboot-publish/reports/figures/2026_09_13_radio20_30ms_visit_readiness')


def read(p): return json.loads(p.read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    deployment=BASE/'deploy30-two-visits-v1/result.json'
    # Deployment results are private to the privileged deployment operator.
    deployed=json.loads(subprocess.check_output(['sudo','-n','cat',str(deployment)]))
    assert deployed['outcome']=='success' and deployed['returned_serial']=='1040005e0b100007100010000bf33a5d4d'
    rejected=BASE/'two-frequency-visits30-v1'
    retry=read(BASE/'two-frequency-visits30-v2/operator.json')
    assert retry['status']=='admission_refused' and retry['rf_samples_collected']==0
    failed=read(rejected/'operator.json')
    assert failed['before']==failed['after'] and failed['temporary_files_removed']
    assert read(rejected/'stdout.json')['result']==-2
    assert (rejected/'visits.txt').read_text().splitlines()[-1]=='terminal -2'
    assert all(value is None for name,value in failed['artifacts'].items() if name.startswith('visit-'))
    junit=BASE/'two-frequency-boot-epoch-tests-v2.xml'
    suite=ET.parse(junit).getroot().find('testsuite')
    result={'scope':'30MS_deployment_and_boot_epoch_admission_fix','native_tracking_qualified':False,
        'corrected_30MS_visits_executed':False,'new_RF_captures':0,
        'fw_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=FW,text=True).strip(),
        'deployment':deployed,'initial_probe_refusal':failed,'initial_probe_status':read(rejected/'stdout.json'),
        'corrected_retry_refusal':retry,
        'tests':{k:suite.attrib[k] for k in ('tests','failures','errors','skipped','time')},
        'operator_admission_tests':read(BASE/'two-frequency-multirate-admission-tests-v1.json'),
        'binary_sha256':digest(BASE/'glrt-cpu-visit-probe-v3'),'sources':{}}
    for name in ('qualify_two_frequency_visits_multirate.py','qualify_two_frequency_visits_boot_epoch.py',
                 'review_two_frequency_boot_visit.py','review_two_frequency_boot_sequence.py','record_30ms_visit_readiness.py'):
        shutil.copyfile(BASE/name,OUT/name);result['sources'][name]=digest(OUT/name)
    shutil.copyfile(junit,OUT/junit.name)
    result['status']='30MS_deployed_boot_epoch_fix_tested_corrected_capture_pending'
    (OUT/'evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(OUT),'sha256':digest(OUT/'evidence.json'),'tests':result['tests'],'fw_commit':result['fw_commit']}))


if __name__=='__main__':main()
