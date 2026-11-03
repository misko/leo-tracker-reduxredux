"""Mark transferred candidates feasible-only; audit frozen input binding."""
import csv
import json
from pathlib import Path
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from experiment import SID, selection

here=Path(__file__).resolve().parent
snapshot=json.loads((here.parent/'2026_10_07_recent_filter_review/snapshot.json').read_text())
doc=next(c['regional_document'] for c in snapshot['captures'] if c['session_id']==SID)
store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
try: source=store.load(SID)
finally: store.close()
assert source.input_manifest_sha256==doc['input_manifest_sha256']
assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
result=json.loads((here/'results.json').read_text())
rows=result['rows']
for row in rows:
    if row['start']=='zero-incumbent-envelope':
        row['stationarity']=None
        row['stop_reason']='feasible-only-transfer'
result['selected']['fitted-c-direct']=selection([r for r in rows if r['arm']=='fitted-c' and r['start']!='zero-incumbent-envelope'])
result['selected']['fitted-c-final-envelope']=result['selected']['fitted-c']
assert result['selected']['fitted-c']['selection_score']<=result['selected']['zero-c']['selection_score']
result['input_binding_verified']={'input_manifest_sha256':source.input_manifest_sha256,'analysis_manifest_sha256':source.analysis_manifest_sha256}
result['zero_incumbent_only']=selection([r for r in rows if r['arm']=='fitted-c' and r['start'] in ('saved-incumbent','zero-incumbent-envelope')])
result['total_fit_elapsed_s']=sum(r['elapsed_s'] for r in rows if r['start'] in ('saved-free','saved-zero'))
(here/'results.json').write_text(json.dumps(result,indent=2))
with (here/'results.csv').open('w') as f:
    fields=[k for k in rows[0] if k!='vector'];writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
print('Binding verified; total fit seconds',result['total_fit_elapsed_s'])
