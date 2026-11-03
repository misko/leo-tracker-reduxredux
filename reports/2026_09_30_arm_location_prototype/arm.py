"""Bounded physical ARM scoring replay; saved orbit inputs, no RF."""
import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from check import compare

HERE=Path(__file__).resolve().parent
ROOT='/mnt/glrtbench/location-prototype-20260930'
SSH=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
OPTIONS=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null']

def remote(cmd,timeout=60):
    return subprocess.check_output([*SSH,'ssh',*OPTIONS,'root@192.168.1.15',cmd],text=True,timeout=timeout)

def upload(path):
    subprocess.run([*SSH,'scp','-O',*OPTIONS,str(path),'root@192.168.1.15:'+ROOT+'/'+path.name],check=True,capture_output=True,timeout=120)
    assert remote('sha256sum '+ROOT+'/'+path.name).split()[0]==hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    local=HERE/'local';m=json.loads((HERE/'inputs.json').read_text())
    remote('mkdir -p '+ROOT)
    (HERE/'arm-device-before.txt').write_text(remote('date -u; uptime; cat /proc/cpuinfo; cat /proc/meminfo'))
    upload(local/'score-arm');remote('chmod +x '+ROOT+'/score-arm')
    reports={}
    for step in (10,30,60):
        f=local/f'ephemeris-{step}.bin';upload(f)
        output=remote('ulimit -v 180000; '+ROOT+'/score-arm '+ROOT+'/'+f.name,120)
        (HERE/f'arm-{step}.json').write_text(output)
        result=json.loads(output);host=json.loads((HERE/f'host-{step}.json').read_text())
        reports[str(step)]=dict(cpu_seconds=result['cpu_seconds'],wall_seconds=result['wall_seconds'],peak_rss_kib=result['peak_rss_kib'],host_arm_points_identical=result['points']==host['points'],comparisons=compare(m,result))
        print(step,'seconds',result['wall_seconds'],'RSS KiB',result['peak_rss_kib'],[(x['candidate_matches'],x['tau_matches'],x['score_delta_hz']) for x in reports[str(step)]['comparisons']],flush=True)
    (HERE/'arm-comparison.json').write_text(json.dumps(reports,indent=2)+'\n')

if __name__=='__main__':main()
