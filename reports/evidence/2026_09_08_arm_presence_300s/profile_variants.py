"""Profile the existing worker's selected saved slices on the verified USB spare."""
from pathlib import Path
import json
import re
import shlex
import subprocess

import numpy as np

from lan_access import call, transfer
from pluto_plus.inventory import scan_local_usb_plutos
from pluto_plus.radio_lock import acquire_radio_lock
from tools.native_presence import ROOT, build_executable
from tools.presence_fftw import fftw_options
from tools.qualify_native_presence import digest, write_json
from tools.qualify_presence_worker import compare_values

root=Path('/tmp/leo-presence-arm-profile.UuBXXp')
out=root/'variants'
out.mkdir(exist_ok=False)
previous=Path('/tmp/leo-presence-holdout.8JIL7Y/arm')
source=Path('/tmp/leo-native-presence-holdout-v1-20260908')
serial='winbond-db620818a328172c'
compiler='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
protocol_path=ROOT/'config/analysis/arm-presence-native-tone-ci16-v1.json'
protocol=json.loads(protocol_path.read_text())
flags=tuple(protocol['common_flags'])+tuple(f'-DLEO_PRESENCE_{k}={v}' for k,v in protocol['variants'][0]['defines'].items())+(
    '-DLEO_PRESENCE_DIFFERENTIAL_CI16=1','-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1')
fftw=fftw_options(Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot/usr'),runtime_rpath=False)
desktop=fftw_options(Path('/tmp/leo-presence-fftw.nLw4v6/install'))
records=[]
for rate in (2500000,5000000):
    manifest=json.loads((previous/f'{rate}-amplitude-diverse.manifest.json').read_text())
    for record in manifest['records'][:8]:
        selected=record['expected']['rank']['order'][0]
        name=record['source_files'][selected]
        assert digest(source/name)==record['source_sha256'][selected]
        records.append(dict(record,probe=name,selected=selected))
variants={'baseline':(0,0),'magnitude':(1,0),'blocked':(0,1),'combined':(1,1)}
freeze=dict(records=records,recipe_sha256=digest(Path(__file__)),protocol_sha256=digest(protocol_path),variants=variants,
            scope='Selected original slices of first eight dwells per rate, five repetitions; no RF or new search policy',
            target=serial,lan='192.168.1.14',repeats=5)
write_json(out/'freeze.json',freeze)
for name,(magnitude,block) in variants.items():
    options=flags+(f'-DLEO_PRESENCE_BOUNDED_MAGNITUDE={magnitude}',f'-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION={block}')
    build_executable(out/f'{name}-arm',compiler=compiler,cflags=options+('-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard')+fftw['cflags'],
                     ldflags=fftw['ldflags'],dependencies=fftw['dependencies'])
    build_executable(out/f'{name}-desktop',cflags=options+desktop['cflags'],ldflags=desktop['ldflags'],dependencies=desktop['dependencies'])
library=Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot/usr/lib/libfftw3.so.3.6.10')
paths={**{f'{name}-arm':out/f'{name}-arm' for name in variants},'libfftw3.so.3':library,**{r['probe']:source/r['probe'] for r in records}}
hashes={name:digest(path) for name,path in paths.items()}


def remote_checked(label,command,timeout=15):
    result=call(command,timeout=timeout)
    write_json(out/f'{label}.json',dict(command=command,stdout=result.stdout,stderr=result.stderr,returncode=result.returncode))
    assert result.returncode==0, result.stderr
    return result.stdout


def check(label):
    usb=[d for d in scan_local_usb_plutos() if d.serial==serial]
    assert len(usb)==1 and usb[0].usb_path=='/sys/bus/usb/devices/5-1'
    assert remote_checked(label+'-serial','cat /sys/kernel/config/usb_gadget/*/strings/0x409/serialnumber').strip()==serial
    assert remote_checked(label+'-buffers','cat /sys/bus/iio/devices/iio:device*/buffer/enable').split()==['0','0']
    remote_checked(label+'-state','cat /proc/loadavg\nnetstat -nt\nps')


rows=[]
with acquire_radio_lock(serial):
    check('before')
    remote=remote_checked('scratch','mktemp -d /tmp/leo-glrt-profile.XXXXXX').strip()
    assert re.fullmatch(r'/tmp/leo-glrt-profile\.[A-Za-z0-9]{6}',remote)
    for name,path in paths.items():
        sent=transfer([path],f'{remote}/{name}')
        assert sent.returncode==0,sent.stderr
    remote_files=' '.join(shlex.quote(f'{remote}/{name}') for name in paths)
    got=remote_checked('initial-hashes','sha256sum '+remote_files)
    assert {Path(line.split()[1]).name:line.split()[0] for line in got.splitlines()}==hashes
    for index,record in enumerate(records):
        desk=subprocess.run([str(out/'baseline-desktop'),str(source/record['probe']),'1','--nuisance'],check=True,text=True,capture_output=True)
        expected=json.loads(desk.stdout)
        assert len(expected['candidates'])==len(record['expected']['candidates'])
        for a,b in zip(expected['candidates'],record['expected']['candidates'],strict=True): compare_values(a,b)
        for name in variants if index%2==0 else reversed(variants):
            command=f'LD_LIBRARY_PATH={remote} nice -n 10 {remote}/{name}-arm {remote}/{record["probe"]} 5 --nuisance'
            raw=remote_checked(f'run-{index:02}-{name}',command,timeout=20)
            arm=[json.loads(line) for line in raw.splitlines()]
            assert len(arm)==5
            for row in arm:
                assert row['device_counter']==str(int(record['counter'])+record['selected']*record['rate_hz']//50)
                assert len(row['candidates'])==len(expected['candidates'])
                for a,b in zip(row['candidates'],expected['candidates'],strict=True): compare_values(a,b)
                compare_values({k:v for k,v in row['nuisance'].items() if k!='cpu_ms'},expected['nuisance'],nuisance=True)
            rows.append(dict(record=record,variant=name,desktop=expected,arm=arm))
        print(f'Profiled {index+1}/16 selected saved slices, four variants and five ARM repetitions',flush=True)
    check('after')
    got=remote_checked('final-hashes','sha256sum '+remote_files)
    assert {Path(line.split()[1]).name:line.split()[0] for line in got.splitlines()}==hashes
    remote_checked('cleanup-files','rm '+remote_files)
    remote_checked('cleanup-directory','rmdir '+shlex.quote(remote))
write_json(out/'results.json',rows)
summary={}
for rate in (2500000,5000000):
    summary[str(rate)]={}
    for name in variants:
        subset=[row for r in rows if r['record']['rate_hz']==rate and r['variant']==name for row in r['arm']]
        fields={k:[r[k] for r in subset] for k in ('conversion_cpu_ms','coarse_cpu_ms','fine_cpu_ms','fractional_cpu_ms','total_cpu_ms','total_wall_ms')}
        fields.update({k:[r['profile'][k] for r in subset] for k in subset[0]['profile'] if k.endswith('_ms')})
        fields['tone_cpu_ms']=[r['nuisance']['cpu_ms'] for r in subset]
        summary[str(rate)][name]={k:dict(zip(('mean','p50','p99','max'),[float(np.mean(v)),*np.percentile(v,[50,99,100]).tolist()],strict=True)) for k,v in fields.items()}
write_json(out/'summary.json',summary)
assert freeze['recipe_sha256']==digest(Path(__file__))
assert all(digest(p)==hashes[n] for n,p in paths.items())
print(json.dumps(summary,indent=2))
