"""Challenge fixed assignments with every discovered satellite timing mode.

Development diagnostic only: discovery and calibration used the complete scan.
Alternative modes need not own these peaks in the original decoder. This is a
conservative local identity challenge, not a globally feasible reassignment.
"""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,digest
from compare_decoders import coherence_filter


def challenge(own_score,own_number,scores,numbers):
    other=np.flatnonzero(np.asarray(numbers)!=own_number)
    valid=other[np.isfinite(np.asarray(scores)[other])]
    if not len(valid):return None,None,True
    best=int(valid[np.argmax(np.asarray(scores)[valid])])
    margin=float(own_score-scores[best])
    return best,margin,bool(margin>=np.log(10))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    label=parser.parse_args().scan;started=time.monotonic();folder=ROOT/'development-comparison'
    with np.load(folder/f'{label}-inputs.npz') as archive:a={k:archive[k] for k in archive.files}
    metadata=json.loads((folder/f'{label}-inputs.json').read_text())
    source=ROOT/'development-discovery'/f'{label}-proposals.json'
    discovery=json.loads(source.read_text());proposals=discovery['proposals']
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import Case,circular_residual
    case=Case(label);params=a['parameters'].copy();coefficient=a['coefficient']
    residual=np.empty((len(a['rows']),len(proposals)));visibility=np.empty(residual.shape,bool)
    for col,p in enumerate(proposals):
        index=p['satellite_index'];params[6+index]=p['total_timing_s']
        prediction,visible=case.predict([index],params,coefficient)
        residual[:,col]=circular_residual(case.data.measured[a['rows']],prediction[a['rows'],0],case.prepared.alias_hz)
        visibility[:,col]=visible[a['rows'],0]
        if (col+1)%200==0:print(label,'identity modes',col+1,'/',len(proposals),flush=True)
    numbers=np.array([p['catalog_number'] for p in proposals]);offset=np.array([p['offset_s'] for p in proposals])
    fixed_offset=np.array([p['offset_s'] for p in metadata['proposals']])
    lookup={int(r):i for i,r in enumerate(a['rows'])};columns={int(n):i for i,n in enumerate(a['numbers'])}
    output=ROOT/'development-identity-modes';output.mkdir(exist_ok=True);summaries=[]
    for method in ('activity','history','tracklet'):
        result_path=folder/f'{label}-{method}.json';result=json.loads(result_path.read_text())
        pairs=[(lookup[r['row_index']],columns[r['catalog_number']]) for r in result['records']]
        _,segments=coherence_filter(pairs,a['times'],a['receiver'],a['channel'])
        details=[];accepted=[];newly_rejected=0
        previously={r['row_index'] for r in result['records'] if r['identity_screen_pass']}
        for col,rows in segments:
            scores=-.5*np.sum((residual[rows]/200)**2,axis=0)-.5*offset**2
            scores[~np.all(visibility[rows],axis=0)]=-np.inf
            own=-.5*np.sum((a['residual'][rows,col]/200)**2)-.5*fixed_offset[col]**2
            number=int(a['numbers'][col]);best,margin,passes=challenge(own,number,scores,numbers)
            # Retain the earlier fixed-mode challenge too: expanding the
            # alternative set must never upgrade a previously rejected segment.
            was_accepted=all(int(a['rows'][r]) in previously for r in rows)
            passes=passes and was_accepted
            if passes:accepted.extend(map(int,a['rows'][rows]))
            elif was_accepted:newly_rejected+=len(rows)
            details.append(dict(catalog_number=number,receiver=int(a['receiver'][rows[0]]),
                channel=int(a['channel'][rows[0]]),start_s=float(a['times'][rows[0]]),
                end_s=float(a['times'][rows[-1]]),groups=len(rows),own_score=float(own),margin=margin,
                alternative=None if best is None else dict(catalog_number=int(numbers[best]),
                    offset_s=float(offset[best]),proposal_index=best),
                previous_pass=was_accepted,passes=passes,rows=a['rows'][rows].tolist()))
        summary=dict(scan=label,method=method,denominator=len(a['rows']),
            previous_screened=result['identity_screen_assigned'],mode_screened=len(accepted),
            mode_screened_coverage=len(accepted)/len(a['rows']),newly_rejected=newly_rejected,
            modes_tested=len(proposals),catalogs_tested=len(set(numbers)),elapsed_s=time.monotonic()-started)
        payload=dict(summary=summary,scope=__doc__,accepted_rows=accepted,segments=details,
            source_sha256={str(source):digest(source),str(result_path):digest(result_path)},
            limitations=['Only discovered modes, not every continuous timing value or every bank identity.',
                'No nuisance refit per alternative; frozen full-data nuisance calibration.',
                'Local alternative may conflict with other assigned tracks; not proof of a replacement identity.',
                'Not held-out validation or calibrated posterior odds.'])
        (output/f'{label}-{method}.json').write_text(json.dumps(payload,indent=2,allow_nan=False))
        summaries.append(summary)
    print(json.dumps(summaries),flush=True)


if __name__=='__main__':main()
