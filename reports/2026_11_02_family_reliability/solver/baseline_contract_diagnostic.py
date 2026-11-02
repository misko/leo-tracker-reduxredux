"""No-refit diagnosis of inherited fit-union versus published-ownership mismatch."""
import json
from pathlib import Path
from algo07_science import engine as e
from algo06_science.common import read,write
from combined_evidence_audit import inventory,digest

ROOT=Path(__file__).resolve().parent
def main(case='DS26-0104'):
    policy=read(ROOT.parent/'population/protocol.json')
    record=next(r for r in policy['cases'] if r['case']==case)
    data=Path(record['input_path']).parent.parent
    e.configure(data,ROOT);e.ROOTS[case[:4]]=data
    d,z,replay=e.load_case(case);arms={}
    for arm,(p,x) in d['problems'].items():
        actual=inventory(d,p);saved=z['baseline_owners'][arm]
        missing=sorted(set(saved)-set(actual['owners']));extra=sorted(set(actual['owners'])-set(saved))
        changed=[dict(observation_id=o,published=saved[o],fitted=actual['owners'][o]) for o in set(saved)&set(actual['owners']) if saved[o]!=actual['owners'][o]]
        witnesses=[]
        for row,i,sl in zip(p.rows,p.members,p.slices):
            tr=p.scan.tracks[i];local=[(k,o) for k,o in enumerate(tr['observation_ids']) if o in missing]
            if local:witnesses.append(dict(component=row['component'],norad=row['candidate_norad'],
                total_track_points=len(tr['observation_ids']),kept_track_points=int(p.keep[sl].sum()),
                missing_ids=[o for k,o in local],missing_keep_values=[bool(p.keep[sl][k]) for k,o in local],
                missing_times_s=[float(tr['times'][k]) for k,o in local]))
        arms[arm]=dict(published_owner_count=len(saved),fitted_native_union_count=len(actual['ids']),
            fitted_piece_counts=actual['counts'],published_owners_absent_from_fit_union=missing,
            fit_union_ids_absent_from_published_ownership=extra,shared_ids_identity_changes=changed,
            missing_owner_families=sorted(set(saved[o] for o in missing)),extra_fit_families=sorted(set(actual['owners'][o] for o in extra)),
            missing_curved_track_witnesses=witnesses,
            fitted_union_sha256=actual['ids_sha256'],published_owner_ids_sha256=digest(sorted(saved)))
    tracks=read(Path(z['native_path'])/'tracks.json')
    for arm,row in arms.items():
        missing=set(row['published_owners_absent_from_fit_union'])
        row['missing_native_graph_track_witnesses']=[dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],
            total_points=len(t['observation_ids']),missing_published_points=len(missing&set(t['observation_ids'])),
            start_s=float(t['times'][0]),end_s=float(t['times'][-1])) for t in tracks if missing&set(t['observation_ids'])]
    output=dict(case=case,stage='unmodified e.load_case before candidate_context, fit, family selection, or covariance scaling',
        scope='inherited baseline contract diagnostic; no fitting or evaluation geography',replay=replay,arms=arms)
    write(ROOT/f'baseline_contract_{case}.json',output)
    print(json.dumps({a:{k:v for k,v in row.items() if k in ('published_owner_count','fitted_native_union_count','fitted_piece_counts','missing_owner_families','extra_fit_families')} for a,row in arms.items()}))

if __name__=='__main__':main()
