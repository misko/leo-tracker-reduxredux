"""Bounded saved-IQ ARM replay; never opens IIO or changes acquisition."""
from contextlib import ExitStack
from pathlib import Path
import hashlib
import json
import re
import shlex
import struct
import time

import numpy as np

from lan_access import call, transfer
from pluto_plus.inventory import scan_local_usb_plutos
from pluto_plus.radio_lock import acquire_radio_lock
from tools.native_presence import ROOT
from tools.presence_dwell import NativeDwell, unpack
from tools.benchmark_presence_execution import differences, numerical
from tools.qualify_native_presence import digest, write_json
from tools.qualify_presence_dwell_worker import FIELDS, verify

root = Path('/tmp/leo-presence-arm-profile.UuBXXp')
assets = Path('/tmp/leo-presence-holdout.8JIL7Y/arm')
qualification = root / 'qualification'
out = root / 'replay-300s'
out.mkdir(exist_ok=False)
serial = 'winbond-db620818a328172c'
paths = {'parent': assets/'parent',
         'worker-combined': qualification/'worker-combined',
         'worker-baseline': qualification/'worker-baseline',
         'libfftw3.so.3': Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot/usr/lib/libfftw3.so.3.6.10')}
for rate in (2500000, 5000000):
    for kind in ('templates', 'pack'):
        paths[f'{rate}.{kind}'] = assets/f'{rate}.{kind}'
payload = {name: digest(path) for name, path in paths.items()}
builds = {}
for name, path in list(paths.items())[:3] + [(name, qualification/f'{name}.so') for name in ('baseline','combined')]:
    receipt_path = path.with_name(path.name+'.build.json')
    receipt = json.loads(receipt_path.read_text())
    assert receipt['binary_sha256'] == digest(path)
    assert all(digest(ROOT/p) == sha for p, sha in receipt['sources_sha256'].items())
    assert all(digest(Path(p)) == sha for p, sha in receipt.get('dependencies_sha256', {}).items())
    builds[name] = receipt
    write_json(out/f'{name}.build.json', receipt)
freeze = dict(recipe_sha256=digest(Path(__file__)), payload_sha256=payload,
              target=serial, address='192.168.1.14', rx=1, arrival_period_ms=120,
              order=[[5000000,'baseline',30000], [5000000,'combined',300000],
                     [2500000,'combined',300000], [2500000,'baseline',30000]],
              scheduling='nice 10, inherited affinity; saved 32768-sample chunks burst per dwell',
              live_rf=False, deployed=False, firmware_changed=False,
              rtol=1e-9, atol=1e-10,
              scope='Execution parity and 300s worker endurance, not original DMA arrival/load or live duty')
write_json(out/'freeze.json', freeze)

# Check all fields on both full-dwell libraries and against the frozen worker
# manifests before any ARM execution. Preserve the original expected fields.
manifests = {}
with ExitStack() as stack, (out/'desktop-parity.jsonl').open('x') as stream:
    engines = {}
    for rate in (2500000,5000000):
        original_path = assets/f'{rate}-amplitude-diverse.manifest.json'
        manifest = json.loads(original_path.read_text())
        assert manifest['pack_sha256'] == payload[f'{rate}.pack']
        assert manifest['templates_sha256'] == payload[f'{rate}.templates']
        with paths[f'{rate}.pack'].open('rb') as pack:
            magic, packed_rate, count = struct.unpack('<4sII', pack.read(12))
            assert (magic,packed_rate,count)==(b'LDP1',rate,len(manifest['records']))
            assert count == 16
            for meta in manifest['records']:
                header = struct.unpack('<QQII',pack.read(24))
                assert header==(int(meta['counter']),meta['visit'],int(meta['edge']=='upper'),meta['channel'])
                raw = pack.read(rate//50*6*4)
                assert hashlib.sha256(raw).hexdigest()==meta['iq_sha256']
                iq = np.frombuffer(raw,dtype='<i2').reshape(-1,2)
                outputs = {}
                for name in ('baseline','combined'):
                    key = name, rate, meta['edge']
                    if key not in engines:
                        engines[key] = stack.enter_context(NativeDwell(qualification/f'{name}.so',rate,meta['edge'],512))
                    native = engines[key]
                    result = unpack(native.run(iq,maximum=1,seeded=False))
                    screens = unpack(native.screens())
                    outputs[name] = dict(result=result,screens=screens)
                    confirmation = result['confirmations'][0]
                    expected = dict(candidates=[{k:c[k] for k in FIELDS} for c in confirmation['candidates'][:confirmation['candidate_count']]],
                                    nuisance=numerical(result['nuisances'][0]), rank=numerical(result['rank']),
                                    screen_diagnostics=screens, confirmation_window_mask=result['confirmation_window_mask'])
                    assert not differences(meta['expected'], expected), 'frozen manifest differs'
                mismatches = differences(numerical(outputs['baseline']),numerical(outputs['combined']))
                stream.write(json.dumps(dict(rate_hz=rate,visit=meta['visit'],iq_sha256=meta['iq_sha256'],
                                             variants=outputs,mismatches=mismatches),allow_nan=False)+'\n')
                stream.flush()
                assert not mismatches
                assert hashlib.sha256(iq.tobytes()).hexdigest()==meta['iq_sha256']
            assert not pack.read(1)
        for name in ('baseline','combined'):
            adjusted = dict(manifest, worker_sha256=payload[f'worker-{name}'],
                            reference_sha256=builds[name]['binary_sha256'],
                            parent_manifest_sha256=digest(original_path), expected_values='unchanged from parent manifest')
            manifests[rate,name] = adjusted
            write_json(out/f'{rate}-{name}.manifest.json',adjusted)
        print(f'{rate}: all 16 full saved dwells match baseline and frozen manifest',flush=True)
write_json(out/'desktop-parity-summary.json',dict(unique_dwells=32,executions=64,mismatches=0))

remote = None
logs = []
summaries = []

def recorded(label, command, timeout=15):
    result = call(command,timeout=timeout)
    write_json(out/f'{label}.json',dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    logs.append(label)
    if result.returncode:
        raise RuntimeError(f'{label}: remote exit {result.returncode}')
    return result.stdout

def identity_idle(label):
    devices = [d for d in scan_local_usb_plutos() if d.serial==serial]
    assert len(devices)==1 and devices[0].usb_path=='/sys/bus/usb/devices/5-1'
    assert recorded(label+'-serial','cat /sys/kernel/config/usb_gadget/*/strings/0x409/serialnumber').strip()==serial
    assert recorded(label+'-buffers','cat /sys/bus/iio/devices/iio:device*/buffer/enable').split()==['0','0']
    network = recorded(label+'-network','netstat -nt')
    assert all(':22 ' in line and '192.168.1.142:' in line for line in network.splitlines() if line.startswith('tcp'))
    recorded(label+'-state','cat /proc/loadavg\nps\ndf -k /tmp')

try:
    with acquire_radio_lock(serial):
        identity_idle('preflight')
        remote = recorded('scratch','mktemp -d /tmp/leo-glrt-300s.XXXXXX').strip()
        assert re.fullmatch(r'/tmp/leo-glrt-300s\.[A-Za-z0-9]{6}',remote)
        for name,path in paths.items():
            result = transfer([path],f'{remote}/{name}')
            write_json(out/f'transfer-{name}.json',dict(returncode=result.returncode,stderr=result.stderr,source_sha256=payload[name],remote=f'{remote}/{name}'))
            assert result.returncode==0
        hashes = recorded('payload-hashes','sha256sum '+' '.join(shlex.quote(f'{remote}/{name}') for name in paths))
        assert {Path(line.split()[1]).name:line.split()[0] for line in hashes.splitlines()}==payload
        for index,(rate,name,duration) in enumerate(freeze['order']):
            identity_idle(f'before-{index}')
            label = f'{index}-{rate}-{name}'
            command = (f'LD_LIBRARY_PATH={remote} nice -n 10 {remote}/parent {remote}/worker-{name} '
                       f'{remote}/{rate}.templates {remote}/{rate}.pack {duration} 120')
            print(f'Starting {label}: {duration//1000}s saved-IQ worker replay, 120ms arrivals',flush=True)
            started = time.monotonic()
            result = call(command,timeout=duration/1000+40)
            write_json(out/f'{label}.execution.json',dict(command=command,returncode=result.returncode,stderr=result.stderr,observed_elapsed_s=time.monotonic()-started))
            with (out/f'{label}.jsonl').open('x') as stream:
                stream.write(result.stdout)
            try:
                assert result.returncode==0 and not result.stderr
                checked = verify(result.stdout,manifests[rate,name],duration,arrival_period_ms=120)
                rows = [json.loads(line) for line in result.stdout.splitlines()][:-1]
                checked.update(verified=True,raw_sha256=digest(out/f'{label}.jsonl'),
                               delivery_over_120_ms=sum(r['delivery_latency_ms']>120 for r in rows),
                               delivery_over_100_ms=sum(r['delivery_latency_ms']>100 for r in rows))
            except (AssertionError,ValueError,KeyError) as error:
                checked = dict(verified=False,error=str(error))
            write_json(out/f'{label}.verification.json',checked)
            summaries.append(dict(rate_hz=rate,variant=name,duration_ms=duration,**checked))
            write_json(out/'summary.json',dict(runs=summaries,goal_complete=False,scope=freeze['scope']))
            print(json.dumps(summaries[-1]),flush=True)
        identity_idle('postflight')
        hashes = recorded('final-payload-hashes','sha256sum '+' '.join(shlex.quote(f'{remote}/{name}') for name in paths))
        assert {Path(line.split()[1]).name:line.split()[0] for line in hashes.splitlines()}==payload
        assert all(digest(path)==payload[name] for name,path in paths.items())
        # Remove only the unchanged, enumerated uploads in our new RAM scratch.
        recorded('cleanup-files','rm '+' '.join(shlex.quote(f'{remote}/{name}') for name in paths))
        recorded('cleanup-directory','rmdir '+shlex.quote(remote))
        remote = None
finally:
    write_json(out/'end.json',dict(remote_scratch_retained=remote,logs=logs,recipe_unchanged=freeze['recipe_sha256']==digest(Path(__file__))))
assert all(run['verified'] for run in summaries)
