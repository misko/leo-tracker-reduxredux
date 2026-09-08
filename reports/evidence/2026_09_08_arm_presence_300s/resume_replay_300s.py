"""Resume only unrun cases after local summary publication failed; no RF."""
from pathlib import Path
import json
import re
import shlex
import time

from lan_access import call
from pluto_plus.inventory import scan_local_usb_plutos
from pluto_plus.radio_lock import acquire_radio_lock
from tools.qualify_native_presence import digest, write_json
from tools.qualify_presence_dwell_worker import verify

root=Path('/tmp/leo-presence-arm-profile.UuBXXp')
original=root/'replay-300s'
out=root/'replay-300s-resumed'
out.mkdir(exist_ok=False)
freeze=json.loads((original/'freeze.json').read_text())
remote=json.loads((original/'end.json').read_text())['remote_scratch_retained']
assert remote=='/tmp/leo-glrt-300s.cqilQs' and re.fullmatch(r'/tmp/leo-glrt-300s\.[A-Za-z0-9]{6}',remote)
serial=freeze['target']
payload=freeze['payload_sha256']
assert serial=='winbond-db620818a328172c'
assert set(payload)=={'parent','worker-combined','worker-baseline','libfftw3.so.3',
                      '2500000.templates','2500000.pack','5000000.templates','5000000.pack'}
order=freeze['order'][2:]
write_json(out/'freeze.json',dict(recipe_sha256=digest(Path(__file__)),original_freeze_sha256=digest(original/'freeze.json'),
    resume_reason='Exclusive summary writer reused a filename after successful completed 5MS/s run',
    remote=remote,order=order,original_runs_not_restarted=True,live_rf=False))
logs=[]
summaries=[]

def recorded(label,command,timeout=15):
    result=call(command,timeout=timeout)
    write_json(out/f'{label}.json',dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    logs.append(label)
    assert result.returncode==0
    return result.stdout

def identity_idle(label):
    devices=[d for d in scan_local_usb_plutos() if d.serial==serial]
    assert len(devices)==1 and devices[0].usb_path=='/sys/bus/usb/devices/5-1'
    assert recorded(label+'-serial','cat /sys/kernel/config/usb_gadget/*/strings/0x409/serialnumber').strip()==serial
    assert recorded(label+'-buffers','cat /sys/bus/iio/devices/iio:device*/buffer/enable').split()==['0','0']
    network=recorded(label+'-network','netstat -nt')
    assert all(':22 ' in line and '192.168.1.142:' in line for line in network.splitlines() if line.startswith('tcp'))
    state=recorded(label+'-state','cat /proc/loadavg\nps\ndf -k /tmp')
    assert remote not in state, 'prior process still active; do not resume'

def payload_check(label):
    hashes=recorded(label,'sha256sum '+' '.join(shlex.quote(f'{remote}/{name}') for name in payload))
    assert {Path(line.split()[1]).name:line.split()[0] for line in hashes.splitlines()}==payload

try:
    with acquire_radio_lock(serial):
        identity_idle('preflight')
        payload_check('resume-payload-hashes')
        for index,(rate,name,duration) in enumerate(order,start=2):
            identity_idle(f'before-{index}')
            label=f'{index}-{rate}-{name}'
            command=(f'LD_LIBRARY_PATH={remote} nice -n 10 {remote}/parent {remote}/worker-{name} '
                     f'{remote}/{rate}.templates {remote}/{rate}.pack {duration} 120')
            print(f'Starting {label}: {duration//1000}s saved-IQ replay, 120ms arrivals',flush=True)
            started=time.monotonic()
            result=call(command,timeout=duration/1000+40)
            write_json(out/f'{label}.execution.json',dict(command=command,returncode=result.returncode,stderr=result.stderr,observed_elapsed_s=time.monotonic()-started))
            with (out/f'{label}.jsonl').open('x') as stream:
                stream.write(result.stdout)
            manifest=json.loads((original/f'{rate}-{name}.manifest.json').read_text())
            try:
                assert result.returncode==0 and not result.stderr
                checked=verify(result.stdout,manifest,duration,arrival_period_ms=120)
                rows=[json.loads(line) for line in result.stdout.splitlines()][:-1]
                checked.update(verified=True,raw_sha256=digest(out/f'{label}.jsonl'),
                    delivery_over_120_ms=sum(r['delivery_latency_ms']>120 for r in rows),
                    delivery_over_100_ms=sum(r['delivery_latency_ms']>100 for r in rows))
            except (AssertionError,ValueError,KeyError) as error:
                checked=dict(verified=False,error=str(error))
            write_json(out/f'{label}.verification.json',checked)
            summaries.append(dict(rate_hz=rate,variant=name,duration_ms=duration,**checked))
            print(json.dumps(summaries[-1]),flush=True)
        identity_idle('postflight')
        payload_check('final-payload-hashes')
        write_json(out/'summary.json',dict(runs=summaries,goal_complete=False,scope=freeze['scope']))
        # The enumerated unchanged payload is ours, validated at creation and
        # before/after both batches. Remove no other path.
        recorded('cleanup-files','rm '+' '.join(shlex.quote(f'{remote}/{name}') for name in payload))
        recorded('cleanup-directory','rmdir '+shlex.quote(remote))
        remote=None
finally:
    write_json(out/'end.json',dict(remote_scratch_retained=remote,logs=logs))
assert all(run['verified'] for run in summaries)
