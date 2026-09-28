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
    p.add_argument('--recorded-arrivals',action='store_true')
    p.add_argument('--sd-write',action='store_true')
    args=p.parse_args()
    if args.core is not None and args.capture_rate!=2500000:
        raise ValueError('combined GLRT cohort is 2.5 MS/s only')
    if args.sd_write and (args.capture or args.core is None):
        raise ValueError('SD experiment requires saved-IQ GLRT without live capture')
    if not args.name.replace('-','').isalnum() or not 5<=args.seconds<=120 or not 5<=args.capture_seconds<=60:
        raise ValueError('invalid bounded phase')
    out=HERE/args.name; out.mkdir(exist_ok=False)
    rd=ROOT+'/concurrent-'+args.name
    executable='paced-cadence-arm' if args.recorded_arrivals else 'paced-arm'
    extra=' arrival-offsets.txt' if args.recorded_arrivals else ''
    before=time.monotonic_ns(); uptime=remote('cat /proc/uptime').decode(); after=time.monotonic_ns()
    (out/'clock.json').write_text(json.dumps({'host_before_ns':before,'host_after_ns':after,'target_uptime':uptime})+'\n')
    (out/'target-before.txt').write_bytes(remote('cat /proc/interrupts; cat /proc/softirqs; cat /proc/net/dev; cat /proc/diskstats; cat /proc/meminfo; ps'))
    command=f'mkdir {shlex.quote(rd)} && cd {ROOT} && '
    if args.core is not None:
        command+=f'./paced-arm cases-2500000.txt 2500000 {args.jobs} {args.period} {args.core} {args.rx} > {rd}/glrt.jsonl 2> {rd}/glrt.stderr &'
        # Parenthesize to keep cd and PID capture in the intended shell.
        command=f'mkdir {shlex.quote(rd)} && cd {ROOT} && (./{executable} cases-2500000.txt 2500000 {args.jobs} {args.period} {args.core} {args.rx}{extra} > {rd}/glrt.jsonl 2> {rd}/glrt.stderr & gpid=$!; echo $gpid > {rd}/glrt.pid; ./monitor-arm {args.seconds} 220 $gpid > {rd}/cpu.jsonl; wait $gpid; echo $? > {rd}/glrt.exit)'
    else:
        command+=f'./monitor-arm {args.seconds} 220 > {rd}/cpu.jsonl'
    if args.sd_write:
        command=command.replace(f'./monitor-arm {args.seconds} 220 $gpid',
            f'./sd-writer-arm case-024.ci16 {rd}/archive.ci16 500 120 1 > {rd}/sd.jsonl 2> {rd}/sd.stderr & spid=$!; ./monitor-arm {args.seconds} 220 $gpid $spid')
        command=command[:-1]+f'; wait $spid; echo $? > {rd}/sd.exit)'
    (out/'run.json').write_text(json.dumps({**vars(args),'target_directory':rd,'command':command,
        'source_hashes':{n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ['paced.c' if args.recorded_arrivals else 'paced_v1.c',executable,'monitor.c','monitor-arm','capture.py','run_phase.py','cases-2500000.txt'] + (['arrival-offsets.txt'] if args.recorded_arrivals else []) + (['sd_writer.c','sd-writer-arm'] if args.sd_write else [])}},indent=2)+'\n')
    with (out/'remote.stdout').open('wb') as stdout, (out/'remote.stderr').open('wb') as stderr:
        work=subprocess.Popen([*SSH,command],stdout=stdout,stderr=stderr)
        time.sleep(3)
        if args.core is not None:
            for _ in range(15):
                first=remote('head -n 1 '+shlex.quote(rd+'/glrt.jsonl')).strip()
                if first:
                    ready=json.loads(first)
                    if ready['type']!='ready': raise ValueError('no GLRT ready marker')
                    (out/'ready.json').write_text(json.dumps(ready)+'\n')
                    break
                time.sleep(1)
            else: raise RuntimeError('GLRT did not become ready')
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
    if args.sd_write: names+=['sd.jsonl','sd.stderr','sd.exit']
    for name in names: (out/name).write_bytes(remote('cat '+shlex.quote(rd+'/'+name)))
    before=time.monotonic_ns(); uptime=remote('cat /proc/uptime').decode(); after=time.monotonic_ns()
    (out/'clock-after.json').write_text(json.dumps({'host_before_ns':before,'host_after_ns':after,'target_uptime':uptime})+'\n')
    (out/'target-after.txt').write_bytes(remote('cat /proc/interrupts; cat /proc/softirqs; cat /proc/net/dev; cat /proc/diskstats; cat /proc/meminfo; ps'))
    errors=[]
    if work.returncode: errors.append('remote exit')
    if args.core is not None:
        rows=[json.loads(x) for x in (out/'glrt.jsonl').read_text().splitlines()]
        if int((out/'glrt.exit').read_text())!=0: errors.append('GLRT exit')
        if not rows or rows[-1].get('type')!='complete': errors.append('GLRT incomplete')
        if sum(x['type']=='visit' for x in rows)!=args.jobs: errors.append('GLRT job count')
    if args.capture:
        rpath=out/'capture/receipt.json'
        if cap.returncode or not rpath.exists(): errors.append('capture incomplete')
        else:
            r=json.loads(rpath.read_text()); restoration=r['restoration']; t=r['terminal']
            if t['state']!=1 or t['error'] or any(t[k] for k in ['skipped','invalid','cancelled']): errors.append('capture integrity')
            if restoration['expected']!=restoration['observed'] or restoration['expected_kernel_buffers']!=restoration['observed_kernel_buffers'] or not restoration['fastlock_inactive']: errors.append('restoration')
    if args.sd_write:
        if int((out/'sd.exit').read_text()): errors.append('SD writer exit')
        rows=[json.loads(x) for x in (out/'sd.jsonl').read_text().splitlines()]
        if not rows or rows[-1].get('type')!='complete': errors.append('SD incomplete')
    (out/'validity.json').write_text(json.dumps({'passed':not errors,'errors':errors},indent=2)+'\n')
    if errors: raise RuntimeError(errors)
    print('finished',args.name,flush=True)


if __name__=='__main__':main()
