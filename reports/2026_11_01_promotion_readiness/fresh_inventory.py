"""Read-only metadata inventory after DS28; stdout is a compact local receipt."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

from leo.storage.fast_graph_position import FastGraphPositionStore
from leo.storage.fast_graph_position_v4_export import FastGraphPositionStoreV4Export
from leo.storage.fast_graph_position_v5 import FastGraphPositionStoreV5

PARENT = Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds28_revision2/dataset')


def main():
    before=json.loads((PARENT/'manifest.json').read_text());start=before['cutoff_utc_ns'];cutoff=time.time_ns()
    helper=PARENT/'support/raw_inventory.py'
    spec=importlib.util.spec_from_file_location('metadata_inventory',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    # All discoveries in the canonical two live fast roots. This is an explicitly
    # bounded availability cohort, not a claim of a fresh all-storage census.
    roots=[]
    for base in (Path('/srv/bulk/leo/fast-scan-recordings'),Path('/srv/postgres-nvme/fast-scan-recordings')):
        roots.extend(p for p in base.iterdir() if p.is_dir() and p.name.startswith('fast8-auto-20261101-'))
    raw=module.inventory(roots,Path('/srv/bulk/leo'),2**63-1,start_ns=start,dataset_id='FRESH',required_channels=None)
    if raw['discovery_errors']:raise ValueError(raw['discovery_errors'])
    members=[]
    for m in raw['members']:
        if not start<=m['captured_utc_ns']<cutoff:continue
        members.append({k:m[k] for k in ('recording_id','case_id','session_id','session_ids','captured_utc_ns','tracking_inputs')})
        members[-1]['raw_identity_sha256']=m['raw_recording']['identity_sha256']
        members[-1]['manifest_receipts']=[{k:s[k] for k in ('path','sha256')} for s in m['raw_recording']['segments']]
    by_session={s:m for m in members for s in {m['recording_id'],m['session_id'],*m['session_ids']} if s}
    matches=[];store=FastGraphPositionStore('/srv/bulk/leo')
    for j in store.inputs():
        d=json.loads(Path(j['input_path']).read_text());src=d.get('source',d)
        if src.get('session_id') not in by_session:continue
        status=store.status(j['job_id'])
        matches.append(dict(recording_id=by_session[src['session_id']]['recording_id'],job=j,state=(status or {}).get('state'),source_mode=src.get('capture_mode')))
    v4=FastGraphPositionStoreV4Export('/srv/bulk/leo');v5=FastGraphPositionStoreV5('/srv/bulk/leo',incumbent=v4)
    later=[]
    for j in v4.completed_inputs(minimum_completed_utc_ns=start):
        if j['session_id'] not in by_session:continue
        n=v5.job(j);status=v5.status(n['job_id'])
        later.append(dict(recording_id=by_session[j['session_id']]['recording_id'],algo05=j,algo06=n,algo06_state=(status or {}).get('state')))
    print(json.dumps(dict(start_utc_ns=start,cutoff_utc_ns=cutoff,members=members,public_glrt=matches,completed_algo05=later,
        metadata_helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),parent_sha256=hashlib.sha256((PARENT/'manifest.json').read_bytes()).hexdigest(),
        scope='Two canonical live fast roots, whole acquisitions after DS28r2 cutoff; metadata-only; no RF or IQ writes; no inference or error selection'),indent=2))


if __name__=='__main__':main()
