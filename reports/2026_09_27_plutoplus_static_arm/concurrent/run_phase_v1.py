"""One bounded, explicit phase; never changes existing service affinity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

HERE=Path(__file__).resolve().parent
SSH=['sudo','-n','sshpass','-f','/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review/artifacts/device-tool-glrt-ethernet/artifacts/native-lnb-20-20260910/ssh-password',
     'ssh','-o','LogLevel=ERROR','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=yes',
     '-o','UserKnownHostsFile=/tmp/leo-static-arm-access/known_hosts','root@192.168.1.15']
ROOT='/mnt/glrtbench/leo-static-glrt.4jwvdm'


def remote(cmd,timeout=10):
    return subprocess.check_output([*SSH,cmd],timeout=timeout)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('name'); p.add_argument('--capture',action='store_true')
    p.add_argument('--core',type=int,choices=(0,1)); p.add_argument('--rx',type=int,choices=(1,2),default=2)
    p.add_argument('--jobs',type=int,default=500);p.add_argument('--period',type=int,default=120)
    p.add_argument('--seconds',type=int,default=75);p.add_argument('--capture-seconds',type=int,default=45)
    p.add_argument('--capture-rate',type=int,choices=(2500000,10000000),default=2500000)
    args=p.parse_args()
    if not args.name.replace('-','').isalnum() or not 5<=args.seconds<=120 or not 5<=args.capture_seconds<=60:
        raise ValueError('invalid bounded phase')
    out=HERE/args.name; out.mkdir(exist_ok=False)
    rd=ROOT+'/concurrent-'+args.name
    before=time.monotonic_ns(); uptime=remote('cat /proc/uptime').decode(); after=time.monotonic_ns()
    (out/'clock.json').write_text(json.dumps({'host_before_ns':before,'host_after_ns':after,'target_uptime':uptime})+'\n')
    (out/'target-before.txt').write_bytes(remote('cat /proc/interrupts; cat /proc/softirqs; cat /proc/net/dev; cat /proc/diskstats; cat /proc/meminfo; ps'))
    command=f'mkdir {shlex.quote(rd)} && cd {ROOT} && '
    if args.core is not None:
        command+=f'./paced-arm cases-2500000.txt 2500000 {args.jobs} {args.period} {args.core} {args.rx} > {rd}/glrt.jsonl 2> {rd}/glrt.stderr &'
        # Parenthesize to keep cd and PID capture in the intended shell.
        command=f'mkdir {shlex.quote(rd)} && cd {ROOT} && (./paced-arm cases-2500000.txt 2500000 {args.jobs} {args.period} {args.core} {args.rx} > {rd}/glrt.jsonl 2> {rd}/glrt.stderr & gpid=$!; echo $gpid > {rd}/glrt.pid; ./monitor-arm {args.seconds} 220 $gpid > {rd}/cpu.jsonl; wait $gpid; echo $? > {rd}/glrt.exit)'
    else:
        command+=f'./monitor-arm {args.seconds} 220 > {rd}/cpu.jsonl'
    (out/'run.json').write_text(json.dumps({**vars(args),'target_directory':rd,'command':command,
        'source_hashes':{n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ['paced.c','paced-arm','monitor.c','monitor-arm','capture.py','run_phase.py','cases-2500000.txt']}},indent=2)+'\n')
    with (out/'remote.stdout').open('wb') as stdout, (out/'remote.stderr').open('wb') as stderr:
        work=subprocess.Popen([*SSH,command],stdout=stdout,stderr=stderr)
        time.sleep(3)
        if args.capture:
            env={**os.environ,'PYTHONPATH':'/opt/leo-v058-adaptive/1e7bebed663bc2178a1b91af5b98eb55bc97dc84/src'}
            capcmd=['/home/mouse9911/gits/pluto-plus-utils-feature-103/.venv/bin/python',str(HERE/'capture.py'),
                '--seconds',str(args.capture_seconds),'--rate',str(args.capture_rate),'--output',str(out/'capture')]
            # IQ archive name must be unique across phases.
            env['LEO_BENCH_PHASE']=args.name
            with (out/'capture.stdout').open('wb') as cout,(out/'capture.stderr').open('wb') as cerr:
                cap=subprocess.Popen(capcmd,env=env,stdout=cout,stderr=cerr)
                try: cap.wait(timeout=100)
                except subprocess.TimeoutExpired:
                    cap.send_signal(signal.SIGINT); cap.wait(timeout=30)
                (out/'capture.exit').write_text(str(cap.returncode)+'\n')
                print('capture exit',cap.returncode,flush=True)
        work.wait(timeout=130)
    (out/'remote.exit').write_text(str(work.returncode)+'\n')
    names=['cpu.jsonl']+(['glrt.jsonl','glrt.stderr','glrt.exit','glrt.pid'] if args.core is not None else [])
    for name in names: (out/name).write_bytes(remote('cat '+shlex.quote(rd+'/'+name)))
    (out/'target-after.txt').write_bytes(remote('cat /proc/interrupts; cat /proc/softirqs; cat /proc/net/dev; cat /proc/diskstats; cat /proc/meminfo; ps'))
    print('finished',args.name,flush=True)


if __name__=='__main__':main()
