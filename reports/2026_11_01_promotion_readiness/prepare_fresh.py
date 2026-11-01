"""Export five frozen fresh public ALGO06 outcomes through read-only ports."""
import copy
import hashlib
import json
from pathlib import Path

from algo06_prepare import prepare, export_catalogue
from leo.storage.fast_graph_position_v4_export import FastGraphPositionStoreV4Export
from leo.storage.fast_graph_position_v5 import FastGraphPositionStoreV5
from leo.operations.tle_archive import TleArchiveReader

OUT=Path(__file__).resolve().parent


def read(p):return json.loads(Path(p).read_text())
def write(p,z):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(z,indent=2,allow_nan=False)+'\n')


def main():
    inventory=read(OUT/'fresh-inventory.json');root=OUT/'fresh';root.mkdir(exist_ok=True)
    v4=FastGraphPositionStoreV4Export('/srv/bulk/leo');v5=FastGraphPositionStoreV5('/srv/bulk/leo',incumbent=v4)
    rows=[]
    for k,member in enumerate(inventory['members'],1):
        case=f'FRSH-{k:04d}';work=root/'exports'/case
        matching=[r for r in inventory['completed_algo05'] if r['recording_id']==member['recording_id']]
        if len(matching)!=1:raise ValueError('Expected exactly one verified public incumbent')
        row=matching[0];terminal,proof=v5.terminal(row['algo06']);work.mkdir(parents=True,exist_ok=True)
        source=work/'source-export'
        if not source.exists():v4.export_recovery(row['algo05'],source)
        if (work/'inputs/SCAN.json').exists():z=read(work/'inputs/SCAN.json')
        else:z=prepare(work)
        catalogue=export_catalogue(work,z['scan_receipt']['cutoff_utc_ns'],reader=TleArchiveReader(Path('/var/lib/leo/tle')))
        write(root/'catalogues'/(case+'.json'),dict(catalogue,case=case))
        z=copy.deepcopy(z);z['case']=case
        write(root/'inputs'/(case+'.json'),z)
        addition=terminal['candidate']
        if addition:
            target=next(t for t in z['targets'] if t['observation_ids']==addition['target_ids'])
            trial='published_ALGO06';result=dict(decisions={'72h_30s':dict(status='qualified',trial=trial,source=target['fragment_id'])},trials={trial:addition['trial']})
            write(root/'screen'/case/'result.json',dict(targets=[dict(source=target,summaries=[addition['screen']])]))
        else:result=dict(decisions={'72h_30s':dict(status='fallback')},trials={})
        write(root/'position'/case/'result.json',result)
        write(work/'published-algo06.json',terminal)
        rows.append(dict(case=case,recording_id=member['recording_id'],public_receipt=proof,addition=bool(addition),
                         source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                          (root/'inputs'/(case+'.json'),root/'catalogues'/(case+'.json'),root/'position'/case/'result.json')}))
        print(case,'exported; ALGO06 addition',bool(addition),flush=True)
    write(root/'roster.json',dict(rows=rows,selection='All five acquisitions in frozen fresh-inventory; no error or RF selection',
          evaluation_site_confirmed_by_user=True,evaluation_site=[37.849061591561885,-122.48574968092912],
          truth_used_for_inference=False,production_modified=False))


if __name__=='__main__':main()
