"""Instrument SDK, parent and worker on bounded synthetic saved test packs."""
from pathlib import Path
import json
import os
import struct
import subprocess
import numpy as np

from tools.native_presence import ROOT,build_worker
from tools.presence_dwell import NativeDwell,unpack
from tools.qualify_native_presence import digest,write_json
from tools.qualify_presence_dwell_worker import FIELDS
from tools.qualify_scanner_glrt_sdk import build,verify

root=Path('/tmp/leo-glrt-sdk-blocks.XtW3os')
source=Path('/tmp/pytest-of-mouse9911/pytest-3944/glrt-sdk-replay0')
out=root/'sanitizer'
out.mkdir(exist_ok=False)
san=('-fsanitize=address,undefined','-fno-omit-frame-pointer')
parent=build(out/'parent',cflags=san)
config=json.loads((ROOT/'config/analysis/arm-presence-native-tone-ci16-v1.json').read_text())
flags=tuple(config['common_flags'])+tuple(f'-DLEO_PRESENCE_{k}={v}' for k,v in config['variants'][0]['defines'].items())+(
    '-DLEO_PRESENCE_DIFFERENTIAL_CI16=1','-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1',
    '-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1','-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED=1',
    '-DLEO_PRESENCE_BOUNDED_MAGNITUDE=1','-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION=1')
worker=build_worker(out/'worker',cflags=flags+san)
worker.chmod(0o755)
write_json(out/'freeze.json',dict(recipe_sha256=digest(Path(__file__)),parent_sha256=digest(parent),worker_sha256=digest(worker),
    backend='builtin SDK,parent,worker instrumented; no ARM/FFTW instrumentation claim',duration_ms=968,
    variants=[[0,0],[2,40]],rates=[2500000,5000000]))
env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
summaries=[]
for rate in (2500000,5000000):
    records=[]
    pack=source/f'{rate}.pack'
    with pack.open('rb') as stream:
        magic,actual,count=struct.unpack('<4sII',stream.read(12))
        assert (magic,actual,count)==(b'LDP1',rate,4)
        for i in range(count):
            counter,visit,edge,channel=struct.unpack('<QQII',stream.read(24))
            iq=np.frombuffer(stream.read(rate//50*6*4),dtype='<i2').reshape(-1,2)
            with NativeDwell(source/'reference.so',rate,'upper' if edge else 'lower',512) as native:
                result=unpack(native.run(iq,maximum=1,seeded=False))
            selected=result['confirmations'][0]
            records.append(dict(counter=str(counter),visit=visit,channel=channel,edge='upper' if edge else 'lower',rx=1,
                expected=dict(candidates=[{k:c[k] for k in FIELDS} for c in selected['candidates'][:selected['candidate_count']]],rank=result['rank'])))
        assert not stream.read(1)
    manifest=dict(rate_hz=rate,records=records,pack_sha256=digest(pack))
    write_json(out/f'{rate}.manifest.json',manifest)
    for delay,jitter in ((0,0),(2,40)):
        command=[str(parent),str(worker),str(source/f'{rate}.templates'),str(pack),'968',str(delay),str(jitter),'1']
        result=subprocess.run(command,capture_output=True,text=True,env=env,timeout=15)
        record=dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
        write_json(out/f'{rate}-{delay}-{jitter}.execution.json',record)
        assert result.returncode==0 and not result.stderr
        checked=verify(result.stdout,manifest,968,delay_blocks=delay,jitter_ms=jitter,enabled=True)
        write_json(out/f'{rate}-{delay}-{jitter}.verification.json',checked)
        summaries.append(checked)
        print(f'Sanitized {rate},delay{delay},jitter{jitter}: {checked["results"]} results verified',flush=True)
write_json(out/'summary.json',dict(runs=summaries,errors=0,sdk_processes=4,worker_processes=4))
