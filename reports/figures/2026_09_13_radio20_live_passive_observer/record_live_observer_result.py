"""Collect reviewed v12 results into a small, reproducible report manifest."""
import hashlib
import json
from pathlib import Path
import shutil

BASE=Path(__file__).parent
ROOT=BASE/'cpu-live60-passive-observer-v2'
OUT=Path('/home/mouse9911/gits/leo-radio20-reboot-publish/reports/figures/2026_09_13_radio20_live_passive_observer')


def read(path): return json.loads(path.read_text())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    result={'scope':'live_passive_coarse_observer_integration',
        'serial':'1040005e0b100007100010000bf33a5d4d','address':'192.168.1.20',
        'fw_commit':'3948d23fb235de8025e73dae6f8de2a9f3acfd09',
        'host':read(BASE/'passive-observer-live-host-v1/summary.json'),
        'host_independent_review':read(BASE/'passive-observer-live-host-v1/independent-review.json'),
        'live_operator':read(ROOT/'operator.json'),'live_stdout':read(ROOT/'stdout.json'),
        'live_independent_review':read(ROOT/'independent-observer-capture-review.json'),
        'arm_saved_replay':read(BASE/'paced-live-observer-arm-v1-results/operator.json'),
        'arm_saved_replay_review':read(BASE/'paced-live-observer-arm-v1-results/independent-review.json'),
        'arm_saved_replay_binary_sha256':digest(BASE/'paced-live-observer-arm-v1'),
        'native_tracking_qualified':False,'source_files':{}}
    assert result['live_independent_review']['status']=='pass'
    if result['live_stdout']['native_results']:
        result['native_review']=read(ROOT/'native-epoch-estimate-review.json')
        result['paired_review']=read(ROOT/'paired-coherence-review.json')
    for filename in ('review_live_observer.py','review_live_observer_capture.py',
                     'record_live_observer_integration.py','record_live_observer_result.py',
                     'paced_replay_live_observer.c','qualify_paced_live_observer.py','review_paced_live_observer.py'):
        shutil.copyfile(BASE/filename,OUT/filename)
        result['source_files'][filename]=digest(OUT/filename)
    result['live_path']=str(ROOT)
    (OUT/'evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'evidence':str(OUT/'evidence.json'),'sha256':digest(OUT/'evidence.json'),
                      'bytes':(OUT/'evidence.json').stat().st_size,
                      'rf_seconds':result['live_independent_review']['rf_seconds'],
                      'native_results':result['live_stdout']['native_results']}))


if __name__=='__main__': main()
