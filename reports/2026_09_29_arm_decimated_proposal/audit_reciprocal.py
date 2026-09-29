#!/usr/bin/env python3
"""Audit factor-4 cached-reciprocal normalization artifacts."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();checks=[]
for target in ('host','arm'):
    base=ROOT/'builds'/f'{target}-factor4-reciprocal';d=json.loads((base/'build-receipt.json').read_text())
    for name,digest in d['binaries'].items():checks.append((f'binary:{target}:{name}',sha(base/name)==digest))
    for name,digest in d['sources'].items():checks.append((f'source:{target}:{name}',sha(base/name)==digest))
    commands=' '.join(' '.join(x['command']) for x in d['commands'])
    checks.append((f'strict-factor4:{target}','-DLEO_PROPOSAL_DECIMATION=4' in commands and '-fno-fast-math' in commands and '-ffast-math' not in commands))
    if target=='host':checks.append(('host-units',len(d['units'])==3 and all(x['executed'] for x in d['units'])))
arm=ROOT/'builds/arm-factor4-reciprocal/proposal_probe_arm_factor4_reciprocal'
disassembly=subprocess.run(['/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-objdump','-d',str(arm)],text=True,capture_output=True,check=True).stdout
source=(ROOT/'sources/factor4-reciprocal/proposal_probe.c').read_text()
checks += [('arm-vld4-fold','vld4.16' in disassembly),('arm-vector-normalize','vmulq_f32(values.val[0],inverse)' in source and 'vst2q_f32((float *)(time+k),values)' in source),
           ('cached-reciprocals','inverse_support[FRAMES+1]' in source and '1.0f/(float)count' in source),
           ('zero-support-zero','float inverse_support[FRAMES+1]' in source),
           ('baseline-factor4-preserved',(ROOT/'builds/arm-factor4/build-receipt.json').is_file())]
result={'schema':'arm-decimated-proposal-reciprocal-audit/v1','passed':all(v for _,v in checks),'checks':[{'name':k,'passed':v} for k,v in checks]}
(ROOT/'reciprocal-audit.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['passed']:raise SystemExit('audit failed')
