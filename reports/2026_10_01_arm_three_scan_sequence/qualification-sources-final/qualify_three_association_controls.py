"""Physical fixed-site association controls, after the timed replay has terminated."""
import json
import argparse
from pathlib import Path
import shlex
import subprocess

from compare_published_associations import compare
from evaluate_arm_cadence import timing
from leo.native_pipeline.runner import digest
from run_arm_cadence import device_is_busy


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sequence',default='arm-sequence-v1');args=p.parse_args()
    root=Path(__file__).resolve().parents[1];report=root/'reports/2026_10_01_arm_three_scan_sequence'
    prefix=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
    options=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
        '-o','UserKnownHostsFile='+str(root/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    def remote(argv,timeout=90):
        return subprocess.run(prefix+['ssh',*options,'root@192.168.1.15',shlex.join(list(map(str,argv)))],
                              capture_output=True,text=True,check=True,timeout=timeout)
    if not (report/args.sequence/'execution.json').exists() or device_is_busy(remote(['ps']).stdout):
        raise ValueError('wait until recorded cadence has terminated')
    for scan in json.loads((report/'selection.json').read_text())['scans']:
        directory=report/scan['session_id'];authority=directory/'location-authority'
        output=directory/'published-association-arm';output.mkdir()
        device='/mnt/glrtbench/published-'+scan['session_id'];remote(['mkdir',device])
        payloads={'location':Path('/var/tmp/leo-threshold-pgo-v1/leo-location'),
                  'published.loc1':authority/'published-reference.loc1'}
        hashes={}
        for name,path in payloads.items():
            subprocess.run(prefix+['scp','-O',*options,str(path),'root@192.168.1.15:'+device+'/'+name],check=True,timeout=60)
            expected=digest(path);actual=remote(['sha256sum',device+'/'+name]).stdout.split()[0]
            if expected!=actual:raise ValueError('device payload differs')
            hashes[name]=actual
        remote(['chmod','755',device+'/location'])
        result=remote(['/mnt/glrtbench/native-adaptive/current/measure-run','90',device+'/location','score',device+'/published.loc1','1'])
        (output/'scores.json').write_text(result.stdout);(output/'timing.stderr').write_text(result.stderr)
        actual=json.loads(result.stdout);host=json.loads((directory/'published-association-host/scores.json').read_text())
        comparison=compare(json.loads((authority/'authority.json').read_text()),json.loads((authority/'server-reference.json').read_text()),actual)
        receipt={'host_arm_scores_exact':actual==host,'timing':timing(output/'timing.stderr'),
            'payload_sha256':hashes,'server_comparison':comparison,
            'scope':'Identical published memberships and fixed sites isolate association scoring; not end-to-end track recovery or position accuracy'}
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps({'session':scan['session_id'],'host_arm_exact':actual==host,
            'sites':[{k:v for k,v in c.items() if k!='tracks'} for c in comparison]}),flush=True)
        if actual!=host:raise ValueError('physical association control differs')


if __name__=='__main__':main()
