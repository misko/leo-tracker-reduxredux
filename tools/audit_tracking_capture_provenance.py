"""Separate acquisition provenance from the fast adapter's compatibility label."""
import argparse,csv,hashlib
from collections import Counter
from pathlib import Path
from leo.contracts.digests import canonical_digest
from debug_fast_graph_unassociated import read,write


def acquisition_evidence(document,inventory=None,manifests=None):
    source=document.get('source',document)
    if document.get('provenance',{}).get('run_id'):
        if inventory is None or manifests is None:raise ValueError('adapter export needs original acquisition inventory')
        if canonical_digest(inventory)!=source['input_manifest_sha256']:raise ValueError('acquisition inventory digest mismatch')
        if inventory.get('kind')!='fast-scan-source':raise ValueError('unsupported acquisition inventory kind')
        if len(manifests)!=len(inventory['segments']):raise ValueError('incomplete recording manifests')
        for entry,manifest in zip(inventory['segments'],manifests,strict=True):
            if canonical_digest(manifest)!=entry['manifest_digest']:raise ValueError('recording manifest digest mismatch')
        rates={m['sample_rate_hz'] for m in manifests}
        policies={m['configuration']['policy_id'] for m in manifests}
        if len(rates)!=1 or sum(m['window_count'] for m in manifests)!=inventory['window_count']:
            raise ValueError('acquisition sample geometry mismatch')
        rate=next(iter(rates))
        if rate!=source['sample_rate_hz']:raise ValueError('tracking and acquisition sample rates differ')
        return dict(capture_mode='fast',sample_rate_hz=rate,compatibility_capture_mode=source['capture_mode'],
            authority='digest-verified fast-scan-source and all recording manifests',
            recording_name=inventory['recording_name'],acquisition_policies=sorted(policies))
    return dict(capture_mode=source['capture_mode'],sample_rate_hz=source['sample_rate_hz'],
        compatibility_capture_mode=source['capture_mode'],authority='direct scanner tracking contract; no fast compatibility wrapper',
        recording_name=source['session_id'],acquisition_policies=[])


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);hashes={};index={}
    def load(path):
        data=read(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return data
    for path in sorted(args.inventories.glob('*.json')):
        d=read(path)
        if d.get('kind')=='fast-scan-source':index[canonical_digest(d)]=path
    jobs=load(args.study/'systematic-annotation-v1/protocol.json')['rows'];jobs={r['track_id']:r for r in jobs}
    ids=set()
    for path in args.candidates:
        for row in load(path):ids.add(row['track_id'])
    cache={};rows=[]
    for tid in sorted(ids):
        job=jobs[tid];inv=load(Path(job['inventory']));root=Path(inv['job']['root'])/inv['job']['case'];path=root/'tracking.json'
        if str(path) not in cache:
            doc=load(path);source=doc.get('source',doc);inventory=None;manifests=None;input_path=None
            if doc.get('provenance',{}).get('run_id'):
                input_path=index[source['input_manifest_sha256']];inventory=load(input_path)
                manifests=[load(Path(e['path'])/'manifest.json') for e in inventory['segments']]
            cache[str(path)]=dict(**acquisition_evidence(doc,inventory,manifests),source_tracking=str(path),
                acquisition_inventory=str(input_path) if input_path else '')
        rows.append(dict(track_id=tid,scan=job['label'],source_case=inv['job']['case'],**cache[str(path)]))
    write(args.output/'rows.json',rows)
    with (args.output/'capture_provenance.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    write(args.output/'summary.json',dict(curves=len(rows),unique_tracking_sources=len(cache),
        modes=dict(Counter(r['capture_mode'] for r in rows)),
        rates=dict(Counter(str(r['sample_rate_hz']) for r in rows)),
        incompatible_label_count=sum(r['capture_mode']!=r['compatibility_capture_mode'] for r in rows),
        source_hashes=hashes,changes_to_measurements_or_position=False))
    print('modes',dict(Counter(r['capture_mode'] for r in rows)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','inventories','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--candidates',type=Path,nargs='+',required=True)
    run(p.parse_args())
