"""Stage two new DS9 captures then execute the predeclared three-capture ARM replay."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

from prepare_distinct_arm_cadence import prepare_distinct


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    report = root/'reports/2026_10_01_arm_three_scan_sequence'
    qualification = root/'reports/2026_10_01_native_replay_qualification'
    selection = json.loads((report/'selection.json').read_text())['scans']
    baseline = report/selection[0]['session_id']/'staging/receipt.json'
    deadline = time.monotonic()+600
    while not baseline.exists():
        if time.monotonic() > deadline:
            raise TimeoutError('baseline device verification did not complete')
        time.sleep(2)
    prefix = ['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
    options = ['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
               '-o','UserKnownHostsFile='+str(root/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    recordings = []
    templates = json.loads((root/'reports/2026_09_30_arm_ds9_native_comparison/panel.json').read_text())['templates']
    for i, scan in enumerate(selection):
        session = scan['session_id']; directory = report/session
        remote = '/mnt/glrtbench/three-scan-iq-v1/'+session
        if i:
            print('Staging and verifying '+session, flush=True)
            with (directory/'staging.log').open('xb') as log:
                subprocess.run([sys.executable, str(root/'tools/stage_recorded_scan.py'),
                    '/var/tmp/leo-three-iq-'+session, str(directory/'prepared'),
                    str(directory/'staging'), remote], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1650)
        recording = json.loads((directory/'staging/receipt.json').read_text())
        if recording['capture_digest'] != scan['manifest_sha256'] or recording['visits'] != scan['visits']:
            raise ValueError('selection/staging mismatch')
        tle = directory/'native-orbit/selected.tle'
        subprocess.run(prefix+['scp','-O',*options,str(tle),'root@192.168.1.15:'+remote+'/selected.tle'],check=True,timeout=60)
        recording.update(manifest=remote+'/manifest.tsv',authority=remote+'/authority.tsv',tle=remote+'/selected.tle')
        recording['payloads'][recording['tle']] = hashlib.sha256(tle.read_bytes()).hexdigest()
        for edge, kinds in templates.items():
            for kind, info in kinds.items():
                recording['payloads'][f'/mnt/glrtbench/ds9-native-comparison-20260930/{edge}-{kind}.c128'] = info['sha256']
        recordings.append(recording)
        print('Verified full IQ and staged authority for '+session, flush=True)
    prior = qualification/'cadence-four-queue32-v1'
    remote = '/mnt/glrtbench/three-distinct-cadence-v1'
    digest = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    files, protocol = prepare_distinct(json.loads((qualification/'prepared-threshold-full-v1/cadence-base.json').read_text()),
        remote, recordings, digest(prior/'detector'), digest(prior/'controller'))
    output = report/'arm-sequence-v1'; output.mkdir()
    for name, content in files.items():
        p = output/name; p.parent.mkdir(exist_ok=True); p.write_text(content)
    for name in ('detector','controller'):
        (output/name).write_bytes((prior/name).read_bytes())
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    (output/'acceptance-policy.json').write_text(json.dumps({
        'scope':'Distinct recorded-input correctness and cadence evaluation, not continuous RF',
        'expected_visits':[s['visits'] for s in selection], 'queue_capacity':32,
        'maximum_iq_buffers':34, 'maximum_dwell_latency_ms':5000,
        'zero_rejected_or_failed_dwells':True, 'host_score_tolerance_hz':1e-9,
        'server_comparison':'Report detection recall/extra candidates and track/association differences; server algorithm is not numerically identical'
    },indent=2)+'\n')
    print('Starting three distinct ARM scans',flush=True)
    subprocess.run([sys.executable,str(root/'tools/run_arm_cadence.py'),str(output)],check=True)
    print('ARM sequence finished; scientific comparisons still required',flush=True)


if __name__ == '__main__':
    main()
