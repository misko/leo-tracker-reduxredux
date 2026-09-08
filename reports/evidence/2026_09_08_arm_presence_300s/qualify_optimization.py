"""Execution parity on opened synthetic controls; not a new detection holdout."""
from pathlib import Path
from contextlib import ExitStack
import hashlib
import json

from tools.native_presence import ROOT, build_dwell_presence, build_worker
from tools.presence_structured_challenge import generate
from tools.presence_dwell import NativeDwell, unpack
from tools.benchmark_presence_execution import differences, numerical
from tools.presence_fftw import fftw_options
from tools.qualify_native_presence import digest, write_json

root=Path('/tmp/leo-presence-arm-profile.UuBXXp')
out=root/'qualification'
out.mkdir(exist_ok=False)
original=Path('/tmp/leo-presence-holdout.8JIL7Y/challenge')
frozen=json.loads((original/'freeze.json').read_text())
previous=[json.loads(line) for line in (original/'results.jsonl').read_text().splitlines()]
assert len(previous)==len(frozen['cases'])==480
config=json.loads((ROOT/frozen['protocol']['detector_protocol']).read_text())
flags=tuple(config['common_flags'])+tuple(f'-DLEO_PRESENCE_{k}={v}' for k,v in config['variants'][0]['defines'].items())+(
    '-DLEO_PRESENCE_DIFFERENTIAL_CI16=1','-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1',
    '-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1','-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED=1')
names={'baseline':(0,0),'blocked':(0,1),'combined':(1,1)}
fftw=fftw_options(Path('/tmp/leo-presence-fftw.nLw4v6/install'))
arm=fftw_options(Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot/usr'),runtime_rpath=False)
compiler='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
write_json(out/'freeze.json',dict(source_freeze_sha256=digest(original/'freeze.json'),
    source_results_sha256=digest(original/'results.jsonl'),recipe_sha256=digest(Path(__file__)),
    variants=names,cases=480,confirmations=1,rtol=1e-9,atol=1e-10,
    scope='Opened control cohort: numerical execution qualification, not fresh detection qualification'))
libraries={}
for name,(magnitude,block) in names.items():
    options=flags+(f'-DLEO_PRESENCE_BOUNDED_MAGNITUDE={magnitude}',f'-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION={block}')
    libraries[name]=build_dwell_presence(out/f'{name}.so',cflags=options+fftw['cflags'],ldflags=fftw['ldflags'],dependencies=fftw['dependencies'])
    build_worker(out/f'worker-{name}',compiler=compiler,
        cflags=options+('-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard')+arm['cflags'],ldflags=arm['ldflags'],dependencies=arm['dependencies'])
identities={name:digest(path) for name,path in libraries.items()}
totals={name:dict(comparisons=0,numerical_mismatches=0,policy_mismatches=0) for name in names}
with ExitStack() as stack,(out/'results.jsonl').open('x') as output:
    workspaces={}
    for index,(spec,old) in enumerate(zip(frozen['cases'],previous,strict=True)):
        iq,truth=generate(spec,frozen['protocol'])
        sha=hashlib.sha256(iq.tobytes()).hexdigest()
        assert truth==old['truth'] and sha==old['iq_sha256']
        reference=old['variants']['amplitude-diverse']
        expected=numerical(dict(result=reference['result'],screens=reference['screens']))
        variants={}
        for name in names if index%2==0 else reversed(names):
            key=name,spec['rate_hz'],spec['edge']
            if key not in workspaces:
                workspaces[key]=stack.enter_context(NativeDwell(libraries[name],*key[1:],512))
            native=workspaces[key]
            result=unpack(native.run(iq,maximum=1,seeded=False))
            screens=unpack(native.screens())
            mismatches=differences(expected,numerical(dict(result=result,screens=screens)))
            selected=result['confirmations'][0]
            accepted=[c for c in selected['candidates'][:selected['candidate_count']]
                      if c['fractional_complete'] and c['exact_score']>=.175 and c['margin']>=.025]
            policy_mismatch=bool(accepted)!=reference['flagged']
            totals[name]['comparisons']+=1
            totals[name]['numerical_mismatches']+=bool(mismatches)
            totals[name]['policy_mismatches']+=policy_mismatch
            variants[name]=dict(result=result,screens=screens,mismatches=mismatches,policy_mismatch=policy_mismatch)
        assert hashlib.sha256(iq.tobytes()).hexdigest()==sha
        output.write(json.dumps(dict(truth=truth,iq_sha256=sha,variants=variants),allow_nan=False)+'\n')
        output.flush()
        if (index+1)%40==0: print(f'Execution parity checked {index+1}/480 opened cases',flush=True)
assert identities=={name:digest(path) for name,path in libraries.items()}
write_json(out/'summary.json',totals)
print(json.dumps(totals,indent=2))
if any(item['numerical_mismatches'] or item['policy_mismatches'] for item in totals.values()):
    raise RuntimeError('Execution parity failed; all mismatches retained, no tolerance changed')
