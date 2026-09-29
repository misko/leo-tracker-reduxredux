#!/usr/bin/env python3
"""Verify every source hash named by every report receipt exists locally."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REPORTS=ROOT/'reports'; OUT=Path(__file__).resolve().parent/'source-audit.json'
EXCLUDED_QUALIFICATION_PATHS=(
    Path('reports/2026_09_29_arm_wave8_adaptive_q_glrt/host32-unlabeled-preinstrumentation'),
    Path('reports/2026_09_29_arm_wave8_adaptive_q_glrt/host704-unlabeled-preinstrumentation'),
)
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()
catalog={}
for p in REPORTS.rglob('*'):
    if p.is_file() and p.suffix in ('.c','.h'):
        catalog.setdefault(sha(p),[]).append(str(p.relative_to(ROOT)))
receipts=[];excluded_receipts=[];missing=[];references=0
for p in REPORTS.rglob('build-receipt.json'):
    try:data=json.loads(p.read_text())
    except Exception:continue
    sources=data.get('sources')
    if not isinstance(sources,dict):continue
    relative=p.relative_to(ROOT)
    item={'receipt':str(relative),'source_count':len(sources)}
    if any(relative.is_relative_to(prefix) for prefix in EXCLUDED_QUALIFICATION_PATHS):
        excluded_receipts.append(item)
        continue
    receipts.append(item)
    for name,digest in sources.items():
        references+=1
        if digest not in catalog:missing.append({'receipt':item['receipt'],'source':name,'sha256':digest})
result={'schema':'publication-source-audit/v1','receipt_count':len(receipts),
    'source_references':references,'catalog_hashes':len(catalog),
    'missing_count':len(missing),'missing':missing,
    'excluded_qualification_paths':[str(p) for p in EXCLUDED_QUALIFICATION_PATHS],
    'excluded_receipt_count':len(excluded_receipts),
    'excluded_receipts':excluded_receipts}
OUT.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
raise SystemExit(bool(missing))
