"""Read-only clock and capture-pose evidence inventory; never configures services."""
import datetime
import hashlib
import json
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    commands=[
        ['hostname'],
        ['timedatectl','show','--property=NTPSynchronized','--property=NTP','--property=Timezone'],
        ['chronyc','-n','tracking'],
        ['journalctl','-u','chrony.service','--since','2026-09-26 00:00:00 UTC','--until','2026-09-30 00:00:00 UTC','--no-pager','-o','json'],
        ['journalctl','--list-boots','--no-pager'],
        ['sudo','-n','ls','-la','/var/log/chrony'],
    ]
    receipts=[]
    for command in commands:
        now=datetime.datetime.now(datetime.timezone.utc).isoformat()
        result=subprocess.run(command,capture_output=True,text=True,timeout=15)
        receipts.append(dict(command=command,started_utc=now,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    plan_path=ROOT/'reports/2026_09_29_ds10_geographic/plan.json'
    plan=json.loads(plan_path.read_text())
    base=Path('/srv/bulk/leo/capture-pose/gauss-r20-roof-20260926-v1')
    companions=[dict(session_id=s,path=str(base/(s+'.json')),present=(base/(s+'.json')).is_file()) for s in plan['panels']['N24']]
    config_path=Path('/etc/chrony/chrony.conf')
    config=config_path.read_text()
    logging_lines=[line for line in config.splitlines() if line.lstrip().startswith(('log ','logdir ','#log '))]
    paths=[plan_path,config_path,ROOT/'deploy/station/gauss-r20-roof-20260926-v1.json',
           ROOT/'reports/2026_09_27_roof_direction_subset/REPORT.md',ROOT/'reports/2026_09_29_rx_cone_position/README.md',Path(__file__)]
    result=dict(receipts=receipts,ds10_companions=companions,chrony_logging_directives=logging_lines,
                hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/'evidence.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print('Clock receipts:',len(receipts),'pose companions:',sum(r['present'] for r in companions),'of',len(companions))
    for r in receipts:
        if r['command'][-1]=='/var/log/chrony':print(r['returncode'],r['stdout'],r['stderr'])


if __name__=='__main__':main()
