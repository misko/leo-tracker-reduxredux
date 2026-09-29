#!/usr/bin/env python3
"""Audit exact final-score reuse artifacts and bounded source changes."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'2026_09_29_arm_integrated_scorer/builds-fast/host-v3'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();checks=[]
for receipt_path in sorted((ROOT/'builds').glob('*/build-receipt.json')):
    d=json.loads(receipt_path.read_text());base=receipt_path.parent
    for name,digest in d['binaries'].items():checks.append((f'binary:{d["target"]}:{name}',sha(base/name)==digest))
    for name,digest in d['sources'].items():checks.append((f'source:{d["target"]}:{name}',sha(base/name)==digest))
    commands=' '.join(' '.join(x['command']) for x in d['commands'])
    checks.append((f'no-fast-math:{d["target"]}','-fno-fast-math' in commands and '-ffast-math' not in commands))
    if d['target']!='arm':checks.append((f'units:{d["target"]}',len(d['units'])==3 and all(x['executed'] for x in d['units'])))
for name in ('conditioned_czt.c','conditioned_czt.h','fft_full.c','fine_precision.h','src/native_presence/presence.c'):
    checks.append((f'unchanged:{name}',sha(ROOT/'sources'/name)==sha(BASE/name)))
source=(ROOT/'sources/full_search.c').read_text();cohort=(ROOT/'sources/cohort_probe.c').read_text()
checks += [('exact-cfo-bits','memcpy(&bits,&cfo,sizeof(bits))' in source),
           ('key-includes-count','sample_count==count' in source),
           ('window-local-glrt','final_glrt_cache glrt_cache={0}' in source),
           ('window-local-conditioned','final_conditioned_cache conditioned_cache={0}' in source),
           ('physical-counters','actual_executed_glrt_calls' in cohort and 'glrt_cache_hits' in cohort and 'conditioned_cache_hits' in cohort),
           ('logical-conditioned-replay','conditioned_bins_screened+=cache->entries[i].bins_screened' in source and 'conditioned_bins_rechecked+=cache->entries[i].bins_rechecked' in source)]
result={'schema':'arm-final-reuse-audit/v1','passed':all(v for _,v in checks),'checks':[{'name':k,'passed':v} for k,v in checks]}
(ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['passed']:raise SystemExit('audit failed')
