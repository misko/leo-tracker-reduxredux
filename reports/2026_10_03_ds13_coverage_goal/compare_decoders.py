"""Matched three-decoder development comparison, not held-out validation."""
import argparse,importlib.util,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,digest
from feasible_tracklets import select
from sparse_activity import decode


def coherence_filter(pairs,times,receiver,channel):
    kept=[];segments=[]
    keys=sorted({(col,int(receiver[row]),int(channel[row])) for row,col in pairs})
    for col,rx,ch in keys:
        rows=np.array(sorted([r for r,c in pairs if c==col and receiver[r]==rx and channel[r]==ch],key=lambda r:times[r]),int)
        for part in np.split(rows,np.flatnonzero(np.diff(times[rows])>5)+1):
            if len(part)>=10 and times[part[-1]]-times[part[0]]>=5:
                kept.extend((int(r),col) for r in part);segments.append((col,part))
    return kept,segments


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--method',choices=['activity','history','tracklet'],required=True);args=parser.parse_args()
    folder=ROOT/'development-comparison';path=folder/f'{args.scan}-inputs.npz'
    # Materialize once: NpzFile indexing decompresses an array on every access.
    with np.load(path) as archive:
        a={key:archive[key] for key in archive.files}
    metadata=json.loads((folder/f'{args.scan}-inputs.json').read_text());started=time.monotonic()
    if args.method=='activity':
        pairs=decode(a['times'],a['groups'],a['receiver'],a['channel'],a['gain'],a['visible'],float(a['pdet']),beam_width=16)
    elif args.method=='history':
        # Reuse the existing competing-history implementation, with the same
        # arrays as the other methods rather than its legacy frozen-bank loader.
        module_path=OLD/'history/mht.py';spec=importlib.util.spec_from_file_location('coverage_history',module_path)
        m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
        histories,_=m.track(a['times'],a['groups'],a['residual'],a['gain'],lanes=4*a['receiver']+a['channel']-1,
                            beam=16,group_cap=16,top_per_row=3,state=True)
        pairs=[(r,c) for group in histories[0].assignments for r,c in group if c>=0]
    else:
        # Map original row IDs to the shared canonical local-row arrays.
        inverse={int(r):i for i,r in enumerate(a['rows'])};proposals=[]
        for p in metadata['proposals']:
            segments=[{**s,'eligible_rows':[inverse[r] for r in s['eligible_rows']]} for s in p['segments']]
            proposals.append({**p,'segments':segments})
        result=select(proposals,a['groups'],a['times'],float(a['pdet']))
        lookup={int(n):i for i,n in enumerate(a['numbers'])}
        pairs=[(r['row_index'],lookup[r['catalog_number']]) for r in result['assignments']]
    decoding_s=time.monotonic()-started
    assert len(pairs)==len({r for r,c in pairs})
    assert len(pairs)==len({(int(a['groups'][r]),c) for r,c in pairs})
    assert all(np.isfinite(a['gain'][r,c]) for r,c in pairs)
    kept,segments=coherence_filter(pairs,a['times'],a['receiver'],a['channel'])
    screened=[];margins=[]
    offset=np.array([p['offset_s'] for p in metadata['proposals']])
    for col,rows in segments:
        ll=-.5*np.sum((a['residual'][rows]/200)**2,axis=0)-.5*offset**2
        ll[~np.all(a['visible'][rows],axis=0)]=-np.inf
        own=float(ll[col]);ll[col]=-np.inf;other=int(np.argmax(ll));margin=own-float(ll[other])
        accepted=margin>=np.log(10)
        if accepted:screened.extend((int(r),col) for r in rows)
        margins.append(dict(catalog_number=int(a['numbers'][col]),start_s=float(a['times'][rows[0]]),
                            end_s=float(a['times'][rows[-1]]),groups=len(rows),margin=margin,
                            nearest_alternative=int(a['numbers'][other]),passes=bool(accepted)))
    accepted_set=set(screened);coherent_set=set(kept)
    records=[dict(row_index=int(a['rows'][r]),catalog_number=int(a['numbers'][c]),receiver=int(a['receiver'][r]),
                   channel=int(a['channel'][r]),time_s=float(a['times'][r]),residual_native_hz=float(a['residual'][r,c]),
                   coherent=(r,c) in coherent_set,identity_screen_pass=(r,c) in accepted_set) for r,c in pairs]
    result=dict(scope=__doc__,scan=args.scan,method=args.method,shared_inputs_sha256=digest(path),
                candidate_count=len(a['numbers']),raw_assigned=len(pairs),coherent_assigned=len(kept),
                identity_screen_assigned=len(screened),denominator=len(a['rows']),
                raw_coverage=len(pairs)/len(a['rows']),screened_coverage=len(screened)/len(a['rows']),
                decoding_s=decoding_s,total_s=time.monotonic()-started,records=records,segments=margins,
                warning='Identity margins compare the common fixed timing mode for every retained candidate, not all alternative timing modes. No held-out or negative-control pass; these counts are NOT certified defensible coverage.')
    (folder/f'{args.scan}-{args.method}.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','segments')}),flush=True)


if __name__=='__main__':main()
