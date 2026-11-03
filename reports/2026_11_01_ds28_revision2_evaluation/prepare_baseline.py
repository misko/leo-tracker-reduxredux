"""Read-only public-port inventory and exact private exports; no evaluation truth."""
import json
from pathlib import Path
from leo.storage.fast_graph_position_v3_export import FastGraphPositionStoreV3Export
from leo.storage.fast_graph_position_v4 import FastGraphPositionStoreV4

ROOT=Path(__file__).resolve().parent
WORK=Path('/srv/bulk/leo/research/ds28-r2-causal-variants-20261101')
def read(p):return json.loads(Path(p).read_text())
def write(p,z):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(z,indent=2,allow_nan=False)+'\n')

def main():
    manifest=read(ROOT/'dataset/manifest.json')
    assert manifest['dataset_id']=='DS28'
    store=FastGraphPositionStoreV3Export('/srv/bulk/leo')
    latest=FastGraphPositionStoreV4('/srv/bulk/leo',incumbent=store)
    jobs=list(store.completed_inputs(minimum_completed_utc_ns=manifest['start_utc_ns']))
    rows=[]
    for member in manifest['members']:
        identities={member['recording_id'],member.get('session_id'),*member.get('session_ids',[])}
        options=[j for j in jobs if j['session_id'] in identities]
        row=dict(case=member['dataset_label'],recording_id=member['recording_id'],state='unavailable',
                 reason='no_completed_ALGO04_public_job',options=len(options))
        if options:
            # Deterministic, independent of fit or geographic outcomes.
            job=sorted(options,key=lambda j:j['job_id'])[0]
            folder=WORK/'baselines'/row['case'];export=folder/'source-export'
            descriptor=read(export/'descriptor.json') if export.exists() else store.export_recovery(job,export)
            terminal,receipt=store.terminal(job)
            assert descriptor['incumbent']==terminal
            row.update(state='ready',job=job,terminal_receipt=receipt,export=str(export))
            v4=latest.job(job);status=latest.status(v4['job_id'])
            if status and status['state']=='complete':
                published,pubreceipt=latest.terminal(v4)
                write(folder/'published-algo05.json',published)
                row.update(published_ALGO05_receipt=pubreceipt)
        rows.append(row)
        print(row['case'],row['state'],flush=True)
    write(ROOT/'baseline-roster.json',dict(cases=rows,manifest_sha256=__import__('hashlib').sha256((ROOT/'dataset/manifest.json').read_bytes()).hexdigest(),
                                         source_port='FastGraphPositionStoreV3Export',no_GPS=True))

if __name__=='__main__':main()
