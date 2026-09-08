"""Bounded builtin-backend ASan/UBSan/leak and full-output parity checks."""
from pathlib import Path
import json
import os
import subprocess
import numpy as np

from tools.native_presence import ROOT, build_dwell_presence, write_templates
from tools.presence_dwell import NativeDwell, unpack
from tools.presence_window_rank import write_rank_probe
from tools.qualify_presence_dwell_controls import generate
from tools.evaluate_presence_window_rank import load_dwells
from tools.qualify_native_presence import digest, write_json
from tools.benchmark_presence_execution import differences, numerical, digest_bytes

out = Path('/tmp/leo-presence-arm-profile.UuBXXp/sanitizer')
out.mkdir(exist_ok=False)
source = Path('/tmp/leo-native-presence-holdout-v1-20260908')
config = json.loads((ROOT/'config/analysis/arm-presence-native-tone-ci16-v1.json').read_text())
common = tuple(config['common_flags']) + tuple(f'-DLEO_PRESENCE_{k}={v}' for k,v in config['variants'][0]['defines'].items()) + (
    '-DLEO_PRESENCE_DIFFERENTIAL_CI16=1','-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1',
    '-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1','-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED=1')
baseline = build_dwell_presence(out/'baseline.so',cflags=common+(
    '-DLEO_PRESENCE_BOUNDED_MAGNITUDE=0','-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION=0'))
sanitized = build_dwell_presence(out/'combined-sanitized',executable=True,cflags=common+(
    '-DLEO_PRESENCE_BOUNDED_MAGNITUDE=1','-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION=1',
    '-fsanitize=address,undefined','-fno-omit-frame-pointer'))
write_json(out/'freeze.json',dict(recipe_sha256=digest(Path(__file__)),baseline_sha256=digest(baseline),
    sanitized_sha256=digest(sanitized),backend='builtin only; external FFTW/ARM not instrumented',
    repeats=2,confirmations=6,rtol=1e-9,atol=1e-10,scope='memory safety and execution parity, not detector qualification'))
cases = []
for rate in (2500000,5000000):
    write_templates(out/f'{rate}.templates',rate)
    for edge in ('lower','upper'):
        signal,_ = generate(rate,edge,779,'pilot_plus_tone',3)
        extrema = np.empty_like(signal)
        extrema[::2] = [-32768,32767]
        extrema[1::2] = [32767,-32768]
        for kind,iq in [('pilot_plus_tone',signal),('zero',np.zeros_like(signal)),('extrema',extrema)]:
            cases.append((rate,edge,kind,iq,2**64-1-len(iq)))
seen = set()
for meta,iq in load_dwells(source):
    geometry = meta['rate_hz'],meta['edge']
    if geometry not in seen:
        seen.add(geometry)
        cases.append((*geometry,'saved',iq,2**53+19))
    if len(seen)==4:
        break
assert len(cases)==16 and len(seen)==4

def subset(expected,actual):
    if isinstance(actual,dict):
        return {k:subset(expected[k],v) for k,v in actual.items()}
    if isinstance(actual,list):
        assert len(expected)==len(actual)
        return [subset(a,b) for a,b in zip(expected,actual,strict=True)]
    return expected

env = dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
errors=[]
for index,(rate,edge,kind,iq,counter) in enumerate(cases):
    before=digest_bytes(iq.tobytes())
    probe=out/f'{rate}-{edge}-{kind}.rank'
    write_rank_probe(probe,iq,rate,edge,counter)
    with NativeDwell(baseline,rate,edge,512) as native:
        expected=numerical(unpack(native.run(iq,maximum=6,seeded=False)))
        screens=numerical(unpack(native.screens()))
    for confirmation in expected['confirmations']:
        confirmation['candidates']=confirmation['candidates'][:confirmation['candidate_count']]
    command=[str(sanitized),str(probe),str(out/f'{rate}.templates'),'512','6','blind','2']
    result=subprocess.run(command,env=env,text=True,capture_output=True,timeout=50)
    record=dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,
                iq_sha256=before,mismatches=[])
    try:
        assert result.returncode==0 and not result.stderr
        rows=[json.loads(line) for line in result.stdout.splitlines()]
        assert len(rows)==2
        for iteration,row in enumerate(rows):
            assert row['counter']==str(counter) and row['iteration']==iteration
            assert row['rate_hz']==rate and row['edge']==int(edge=='upper') and row['confirmation_count']==6
            actual=numerical({k:v for k,v in row.items() if k in expected})
            record['mismatches']+=differences(subset(expected,actual),actual)
            record['mismatches']+=differences(screens,numerical(row['screen_diagnostics']))
        assert not record['mismatches'] and digest_bytes(iq.tobytes())==before
    except (AssertionError,ValueError,KeyError) as error:
        errors.append(dict(case=f'{rate}-{edge}-{kind}',error=str(error)))
    write_json(out/f'run-{index:02}.json',record)
    print(f'{index+1}/16 sanitizer processes, {len(errors)} failures',flush=True)
summary=dict(processes=16,dwell_executions=32,confirmations=192,errors=errors,
             scope='builtin backend ASan/UBSan/leak plus same-backend full-output parity')
write_json(out/'summary.json',summary)
print(json.dumps(summary),flush=True)
assert not errors
