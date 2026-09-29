#!/usr/bin/env python3
"""Audit immutable frame-budget build artifacts and scope."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_compile_pack/sources/limited-complex-v2'
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=[]
for receipt_path in sorted((ROOT/'builds').glob('*/build-receipt.json')):
    receipt=json.loads(receipt_path.read_text()); directory=receipt_path.parent
    for name,digest in receipt['binaries'].items():
        checks.append((f'binary:{receipt["target"]}:{name}',sha(directory/name)==digest))
    for name,digest in receipt['sources'].items():
        checks.append((f'source:{receipt["target"]}:{name}',sha(directory/name)==digest))
    commands=' '.join(' '.join(row['command']) for row in receipt['commands'])
    checks.append((f'no-fast-math:{receipt["target"]}',
                   '-fno-fast-math' in commands and '-ffast-math' not in commands))
    if receipt['target']!='sanitizer':
        for budget in (0,1,2,4,8):
            checks.append((f'compiled-budget:{receipt["target"]}:{budget}',
                           f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}' in commands))
    if receipt['target']!='arm':
        checks.append((f'unit:{receipt["target"]}',receipt['unit']['executed'] and
                       'budgets 1/2/4/8' in receipt['unit']['stdout']))
for name in ('full_search.c','full_search.h','src/native_presence/presence.c',
             'conditioned_czt.c','conditioned_czt.h'):
    checks.append((f'unchanged-final-or-boundary:{name}',
                   sha(ROOT/'sources/frame-budget'/name)==sha(BASE/name)))
result={'schema':'arm-frame-budget-audit/v1','passed':all(v for _,v in checks),
        'checks':[{'name':k,'passed':v} for k,v in checks]}
(ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['passed']: raise SystemExit('audit failed')
