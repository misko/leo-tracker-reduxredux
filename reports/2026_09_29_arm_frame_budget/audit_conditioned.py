#!/usr/bin/env python3
"""Verify the conditioned-frame-budget artifacts and unchanged final scorer."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'sources/conditioned-frame-budget'
BASE=ROOT.parent/'2026_09_29_arm_compile_pack/sources/limited-complex-v2'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def between(text, start, end):
    return text[text.index(start):text.index(end)]

checks=[]
for receipt_path in sorted((ROOT/'builds-conditioned').glob('*/build-receipt.json')):
    receipt=json.loads(receipt_path.read_text())
    directory=receipt_path.parent
    for name, value in receipt['binaries'].items():
        checks.append((f'binary:{receipt["target"]}:{name}',digest(directory/name)==value))
    commands=' '.join(' '.join(row['command']) for row in receipt['commands'])
    checks.append((f'no-fast-math:{receipt["target"]}',
                   '-fno-fast-math' in commands and '-ffast-math' not in commands))
    if receipt['target'] != 'sanitizer':
        for budget in (0,1,2,4,8):
            checks.append((f'compiled-default:{receipt["target"]}:{budget}',
                f'-DLEO_CONDITIONED_FRAME_BUDGET_DEFAULT={budget}' in commands))
    if receipt['target'] != 'arm':
        checks.append((f'unit:{receipt["target"]}', receipt['unit']['executed'] and
            'conditioned frame budgets' in receipt['unit']['stdout']))

new=(SOURCE/'full_search.c').read_text()
old=(BASE/'full_search.c').read_text()
checks.append(('final-glrt-source-unchanged', between(new, '/* Compute the three final-ranking',
    'static int full_frame_support') == between(old, '/* Compute the three final-ranking',
    'static int full_frame_support')))
checks.append(('boundary-policy-unchanged', between(new, 'static int boundary_fallback_required',
    'int leo_full_search_run') == between(old, 'static int boundary_fallback_required',
    'int leo_full_search_run')))
result={'schema':'arm-conditioned-frame-budget-audit/v1','passed':all(ok for _,ok in checks),
        'checks':[{'name':name,'passed':ok} for name,ok in checks]}
(ROOT/'conditioned-audit.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['passed']:
    raise SystemExit('audit failed')
