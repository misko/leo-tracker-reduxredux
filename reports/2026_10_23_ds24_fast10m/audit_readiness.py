"""Read-only published-product readiness snapshot, separate from frozen membership."""
import json, hashlib, os
from pathlib import Path
from datetime import datetime,UTC
OUT=Path('/srv/bulk/leo/research/ds24-20261023')
BASE=Path('/srv/bulk/leo')
def read(p):return json.loads(p.read_bytes())
def sha(p):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
members=read(OUT/'sample.json')['selected']
missing={m['recording_id']:m for m in members if not m['tracking_inputs']}
reports={n:[] for n in missing}
for p in (BASE/'fast-scan-reports').glob('*.json'):
    raw=p.read_bytes()
    if not any(n.encode() in raw for n in missing): continue
    d=json.loads(raw)
    name=d.get('recording_name',d.get('recording_id'))
    if name in reports:reports[name].append(dict(path=str(p),sha256='sha256:'+hashlib.sha256(raw).hexdigest(),session_id=d.get('session_id'),run_id=d.get('run_id'),point_count=len(d.get('points',[]))))
selected={r['recording_id'] for r in read(BASE/'fast-scan-backfill-20261023/selection.json')}
rows=[]
for name,m in missing.items():
    p=BASE/'fast-scan-automatic'/f'{name}.json'
    automatic=read(p) if p.exists() else {}
    rows.append(dict(dataset_label=m['dataset_label'],recording_id=name,
                     frozen_tracking_input_available=False,published_reports=reports[name],
                     source_input_manifests=m['source_inputs'],automatic_job=automatic,
                     automatic_job_path=str(p),automatic_job_sha256=sha(p) if p.exists() else None,
                     selected_for_already_running_backfill=name in selected,
                     readiness=('published_report_available_contract_adaptation_required' if reports[name] else 'no_complete_published_GLRT_contract'),
                     inference_receipt='frozen membership remains unchanged; no IQ or collection work launched'))
doc=dict(dataset_id='DS24',created_utc=datetime.now(UTC).isoformat(),membership_seal_unchanged=True,
         missing_frozen_tracking_count=len(rows),published_report_root=str(BASE/'fast-scan-reports'),rows=rows)
p=OUT/'readiness_audit.json';p.write_text(json.dumps(doc,indent=2)+'\n');os.chown(p,1000,1000)
print([(r['dataset_label'],r['automatic_job'].get('state'),len(r['published_reports']),r['selected_for_already_running_backfill']) for r in rows])
