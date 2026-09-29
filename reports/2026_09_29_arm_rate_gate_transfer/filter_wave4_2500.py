#!/usr/bin/env python3
"""Order-preserving 2.5 MHz filter of the sealed Wave4 host704 reference."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_29_arm_wave4_combined/host704'
OUTPUT=HERE/'reference-wave4-2500'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    source_manifest=json.loads((SOURCE/'manifest.json').read_text())
    source_summary=json.loads((SOURCE/'summary.json').read_text())
    if not source_manifest['complete'] or source_manifest['processed_dwells']!=704:raise ValueError('Wave4 source is not sealed host704')
    rows=[]
    for line in (SOURCE/'rows.jsonl').read_text().splitlines():
        row=json.loads(line)
        if row['context']['rate_hz']==2500000:rows.append((line,row))
    if len(rows)!=152:raise ValueError(f'expected 152 existing 2.5 MHz rows, got {len(rows)}')
    selected=[row['context'] for _,row in rows]
    source_selected=[row for row in source_manifest['selected'] if row['rate_hz']==2500000]
    if selected!=source_selected:raise ValueError('rows/manifest filtered selections differ')
    OUTPUT.mkdir(exist_ok=False)
    (OUTPUT/'rows.jsonl').write_text(''.join(line+'\n' for line,_ in rows))
    manifest={k:v for k,v in source_manifest.items() if k not in ('selected','processed_dwells','processed_windows','rows_sha256')}
    manifest.update({'selected':selected,'processed_dwells':152,'processed_windows':152*22,
        'rows_sha256':sha(OUTPUT/'rows.jsonl'),'derivation':'order-preserving rate_hz == 2500000 filter of sealed Wave4 host704'})
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    bindings={'schema':'arm-wave4-2500-reference/v1','source':str(SOURCE),
        'source_rows_sha256':sha(SOURCE/'rows.jsonl'),'source_manifest_sha256':sha(SOURCE/'manifest.json'),
        'source_summary_sha256':sha(SOURCE/'summary.json'),'source_build_receipt_sha256':sha(SOURCE/'build-receipt.json'),
        'filter_sha256':sha(Path(__file__)),'selection_rule':'retain every existing row whose context.rate_hz equals 2500000; preserve source order',
        'source_dwells':source_summary['dwells'],'filtered_dwells':152,'filtered_windows':152*22,
        'filtered_rows_sha256':sha(OUTPUT/'rows.jsonl'),'filtered_manifest_sha256':sha(OUTPUT/'manifest.json'),
        'binary_sha256':source_summary['binary_sha256'],'build_sha256':source_summary['build_sha256']}
    (OUTPUT/'source-bindings.json').write_text(json.dumps(bindings,indent=2)+'\n')
if __name__=='__main__':main()
