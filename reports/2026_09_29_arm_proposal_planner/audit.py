#!/usr/bin/env python3
"""Audit proposal planner build matrix and timing scope."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=[]
for receipt_path in sorted((ROOT/'builds').glob('*/build-receipt.json')):
    d=json.loads(receipt_path.read_text());base=receipt_path.parent
    for name,digest in d['binaries'].items():checks.append((f'binary:{base.name}:{name}',sha(base/name)==digest))
    for name,digest in d['sources'].items():checks.append((f'source:{base.name}:{name}',sha(base/name)==digest))
    commands=' '.join(' '.join(x['command']) for x in d['commands'])
    checks.append((f'planner-flag:{base.name}',('-DLEO_PROPOSAL_FFTW_MEASURE' in commands)==(d['planner']=='measure')))
    checks.append((f'strict-fp:{base.name}','-fno-fast-math' in commands and '-ffast-math' not in commands))
    if d['target']=='host':checks.append((f'host-units:{base.name}',len(d['units'])==2 and all(x['executed'] for x in d['units'])))
source=(ROOT/'sources/proposal_probe.c').read_text()
planning=source.index('double planning_started=wall_ms()')
reference=source.index('for(int m=0;m<LAG_COUNT;m++)')
window_timer=source.index('double begin=now_ms()',reference)
checks += [('planning-before-reference',planning<reference),('window-timer-after-planning',planning<window_timer),
           ('monotonic-wall','CLOCK_MONOTONIC' in source),('estimate-and-measure','LEO_PROPOSAL_PLAN_FLAG' in source and 'FFTW_MEASURE' in source and 'FFTW_ESTIMATE' in source)]
result={'schema':'arm-proposal-planner-audit/v1','passed':all(v for _,v in checks),'checks':[{'name':k,'passed':v} for k,v in checks]}
(ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['passed']:raise SystemExit('audit failed')
