"""Bounded saved-IQ SDK block replay on a physically verified USB spare."""
from pathlib import Path
import json
import re
import shlex
import subprocess
import time

from lan_access import call,transfer
from pluto_plus.inventory import scan_local_usb_plutos
from pluto_plus.radio_lock import acquire_radio_lock
from tools.qualify_native_presence import digest,write_json
from tools.qualify_scanner_glrt_sdk import build,verify

root=Path('/tmp/leo-glrt-sdk-blocks.XtW3os')
out=root/'arm-runs'
out.mkdir(exist_ok=False)
assets=Path('/tmp/leo-presence-holdout.8JIL7Y/arm')
previous=Path('/tmp/leo-presence-arm-profile.UuBXXp')
compiler='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
parent=build(root/'arm',compiler=compiler,cflags=('-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard'))
paths={'sdk-replay':parent,'libleo-scanner-glrt.so':parent.parent/'libleo-scanner-glrt.so',
       'worker':previous/'qualification/worker-combined',
       'libfftw3.so.3':Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot/usr/lib/libfftw3.so.3.6.10')}
manifests={}
for rate in (2500000,5000000):
    for kind in ('pack','templates'):
        paths[f'{rate}.{kind}']=assets/f'{rate}.{kind}'
    manifests[rate]=json.loads((previous/f'replay-300s/{rate}-combined.manifest.json').read_text())
    assert digest(paths[f'{rate}.pack'])==manifests[rate]['pack_sha256']
    assert digest(paths[f'{rate}.templates'])==manifests[rate]['templates_sha256']
    assert digest(paths['worker'])==manifests[rate]['worker_sha256']
payload={name:digest(path) for name,path in paths.items()}
serial='winbond-db620818a328172c'
# Frozen short matrix first; longer runs are conditional on actual SDK fidelity.
order=[(5000000,False,2,40,15000),(5000000,True,0,0,15000),
       (5000000,True,2,40,15000),(2500000,True,2,40,15000),
       (2500000,True,0,0,15000),(2500000,False,2,40,15000),
       (5000000,True,2,40,300000),(2500000,True,2,40,300000)]
freeze=dict(recipe_sha256=digest(Path(__file__)),payload_sha256=payload,serial=serial,address='192.168.1.14',
    order=order,live_rf=False,firmware_changed=False,deployed=False,
    numerical_reference='Previously qualified combined desktop full-dwell fields; same input packs',
    model='131072-sample blocks,121ms visits including synthetic1ms guard,RX0 sentinel; optional2block event delay and40ms delay every fourth block',
    long_run_gate='All earlier runs verified and enabled short callbacks stay below nominal block period',
    scheduling='nice10 inherited affinity; no original arrival or RF/IRQ load claim')
write_json(out/'freeze.json',freeze)
remote=None
summaries=[]
logs=[]

def recorded(label,command,timeout=15):
    result=call(command,timeout=timeout)
    write_json(out/f'{label}.json',dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    logs.append(label)
    assert result.returncode==0
    return result.stdout

def idle(label):
    devices=[d for d in scan_local_usb_plutos() if d.serial==serial]
    assert len(devices)==1 and devices[0].usb_path=='/sys/bus/usb/devices/5-1'
    assert recorded(label+'-serial','cat /sys/kernel/config/usb_gadget/*/strings/0x409/serialnumber').strip()==serial
    assert recorded(label+'-buffers','cat /sys/bus/iio/devices/iio:device*/buffer/enable').split()==['0','0']
    network=recorded(label+'-network','netstat -nt')
    assert all(':22 ' in line and '192.168.1.142:' in line for line in network.splitlines() if line.startswith('tcp'))
    state=recorded(label+'-state','cat /proc/loadavg\nps\ndf -k /tmp')
    if remote:
        assert remote not in state

def hashes(label):
    values=recorded(label,'sha256sum '+' '.join(shlex.quote(f'{remote}/{name}') for name in paths))
    assert {Path(line.split()[1]).name:line.split()[0] for line in values.splitlines()}==payload

try:
    with acquire_radio_lock(serial):
        idle('preflight')
        remote=recorded('scratch','mktemp -d /tmp/leo-sdk-replay.XXXXXX').strip()
        assert re.fullmatch(r'/tmp/leo-sdk-replay\.[A-Za-z0-9]{6}',remote)
        for name,path in paths.items():
            result=transfer([path],f'{remote}/{name}')
            write_json(out/f'transfer-{name}.json',dict(returncode=result.returncode,stderr=result.stderr,sha256=payload[name]))
            assert result.returncode==0
        recorded('trusted-payload-modes',f'chmod 755 {remote}/sdk-replay {remote}/worker\nchmod 600 {remote}/2500000.templates {remote}/5000000.templates')
        hashes('initial-hashes')
        for index,(rate,enabled,delay,jitter,duration) in enumerate(order):
            if duration==300000 and any(not r['verified'] or r.get('callback_over_nominal_period',0) for r in summaries):
                write_json(out/f'long-run-{index}-not-started.json',dict(reason='Earlier replay did not meet frozen numerical/callback gate'))
                continue
            idle(f'before-{index}')
            label=f'{index}-{rate}-enabled{int(enabled)}-delay{delay}-jitter{jitter}'
            command=(f'LD_LIBRARY_PATH={remote} nice -n 10 {remote}/sdk-replay {remote}/worker '
                     f'{remote}/{rate}.templates {remote}/{rate}.pack {duration} {delay} {jitter} {int(enabled)}')
            print(f'Starting {label}: {duration//1000}s modeled SDK block replay',flush=True)
            began=time.monotonic()
            result=call(command,timeout=duration/1000+40)
            write_json(out/f'{label}.execution.json',dict(command=command,returncode=result.returncode,stderr=result.stderr,elapsed_s=time.monotonic()-began))
            with (out/f'{label}.jsonl').open('x') as stream:
                stream.write(result.stdout)
            try:
                assert result.returncode==0 and not result.stderr, 'process rejected or emitted stderr'
                checked=verify(result.stdout,manifests[rate],duration,delay_blocks=delay,jitter_ms=jitter,enabled=enabled)
                checked['raw_sha256']=digest(out/f'{label}.jsonl')
            except (AssertionError,ValueError,KeyError) as error:
                checked=dict(verified=False,error=str(error))
            write_json(out/f'{label}.verification.json',checked)
            summaries.append(dict(label=label,**checked))
            print(json.dumps(summaries[-1]),flush=True)
        idle('postflight')
        hashes('final-hashes')
        assert all(digest(path)==payload[name] for name,path in paths.items())
        write_json(out/'summary.json',dict(runs=summaries,live_rf=False,goal_complete=False))
        recorded('cleanup-files','rm '+' '.join(shlex.quote(f'{remote}/{name}') for name in paths))
        recorded('cleanup-directory','rmdir '+shlex.quote(remote))
        remote=None
finally:
    write_json(out/'end.json',dict(remote_scratch_retained=remote,logs=logs,recipe_unchanged=digest(Path(__file__))==freeze['recipe_sha256']))
assert all(r['verified'] for r in summaries)
