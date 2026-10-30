"""Freeze wholly unowned curves made testable by timestamp-only block shifts."""
import argparse,csv,hashlib
from pathlib import Path
from debug_fast_graph_unassociated import read,write


def select_rows(geometry,ledger,original):
    current={r['track_id']:r for r in ledger};source={r['track_id']:r for r in original};rows=[]
    for g in geometry:
        r=current[g['track_id']]
        if g['new_geometry_support']!='True' or g['whole_curve_unowned']!='True':continue
        if (r.get('predictive_recheck_state') or r['state'])!='insufficient_partitions':continue
        base=source[g['track_id']]
        if base['job_id']!=g['job_id'] or base['component']!=g['component']:raise ValueError('geometry identity mismatch')
        rows.append(dict(base,state='queued',known_validation=None,previous_status='insufficient_partitions',
                         previous_annotation_source=r.get('predictive_recheck_source') or r['annotation_source']))
    if len(rows)!=len({r['track_id'] for r in rows}):raise ValueError('duplicate geometry records')
    return sorted(rows,key=lambda r:(-r['points'],r['track_id']))


def run(args):
    sources={}
    def record(p):sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (args.geometry,args.ledger,args.original):record(p)
    rows=select_rows(list(csv.DictReader(args.geometry.open())),list(csv.DictReader(args.ledger.open())),read(args.original)['rows'])
    for r in rows:
        path=Path(r['inventory']);record(path);inv=read(path)
        t=next(t for t in inv['tracks'] if t['track_id']==r['track_id'])
        if not t['current']['wholly_unassociated']:raise ValueError('unused fragment requires separate reconstruction')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(rows=rows,source_hashes=sources,ordering='descending native point count, then immutable track ID',
        selection='new shifted geometry support, wholly unowned, latest recorded status insufficient partitions',
        partition_scheme='shifted_origin_v1',no_GPS_selection=True,no_RF_values_used_to_choose_partition=True,
        block_s=12,guard_s=2,required_distinct_held_sets=3,minimum_training=8,minimum_held=4,
        predictive_only=True,position_inclusion_requires_separate_validation=True))
    print('Frozen candidates:',len(rows),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('geometry','ledger','original','output'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
