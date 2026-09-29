#!/usr/bin/env python3
"""Audit reduced-resolution proposal artifacts and ordering."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();checks=[]
for receipt_path in sorted((ROOT/'builds').glob('*/build-receipt.json')):
    d=json.loads(receipt_path.read_text());base=receipt_path.parent
    for name,digest in d['binaries'].items():checks.append((f'binary:{base.name}:{name}',sha(base/name)==digest))
    for name,digest in d['sources'].items():checks.append((f'source:{base.name}:{name}',sha(base/name)==digest))
    commands=' '.join(' '.join(x['command']) for x in d['commands'])
    checks.append((f'factor:{base.name}',f'-DLEO_PROPOSAL_DECIMATION={d["factor"]}' in commands))
    checks.append((f'strict-fp:{base.name}','-fno-fast-math' in commands and '-ffast-math' not in commands))
    if d['target']=='host':checks.append((f'host-units:{base.name}',len(d['units'])==2 and all(x['executed'] for x in d['units'])))
    else:
        binary=base/f'proposal_probe_arm_factor{d["factor"]}'
        disassembly=subprocess.run(['/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-objdump','-d',str(binary)],text=True,capture_output=True,check=True).stdout
        checks.append((f'arm-vld4:{base.name}','vld4.16' in disassembly))
source=(ROOT/'sources/proposal_probe.c').read_text()
original_fold=source.index('fold_selected(b->fold_time')
observed_average=source.index('block_average(b->time,b->fold_time,original_n,b->decimation)',original_fold)
checks += [('observed-average-after-original-fold',original_fold<observed_average),
           ('template-wrap-original-grid','%(size_t)original_n' in source or ')%original_n' in source),
           ('ceil-reduced-length','original_n+(size_t)b->decimation-1' in source),
           ('mapped-output','return reduced*b->decimation' in source)]
result={'schema':'arm-decimated-proposal-audit/v1','passed':all(v for _,v in checks),'checks':[{'name':k,'passed':v} for k,v in checks]}
(ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['passed']:raise SystemExit('audit failed')
