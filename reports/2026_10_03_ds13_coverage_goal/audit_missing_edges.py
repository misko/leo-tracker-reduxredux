"""Recover alternative peak edges inside existing coherent activity proposals.

Keep the original ten-group segment support. Do not count multiple alternatives
as multiple satellite detections; defer their competition to exclusive matching.
Development-only calibration, not validated coverage.
"""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,digest
from audit_proposals import maximum_group_pairs


def eligible_segment_rows(segment,representatives,times,receiver,channel,residual,visible):
    r=np.asarray(representatives,int)
    return r[(receiver[r]==segment['receiver'])&(channel[r]==segment['channel'])
             &(times[r]>=segment['start_s']-1e-7)&(times[r]<=segment['end_s']+1e-7)
             &visible[r]&(np.abs(residual[r])<=600)]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    label=parser.parse_args().scan;start=time.monotonic()
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import Case,circular_residual
    c=Case(label);d=c.data
    source=ROOT/'development-discovery'/f'{label}-proposals.json'
    discovery=json.loads(source.read_text())
    fit_source=OLD/'exhaustive-subset'/f'{label}-receipt.json'
    assert digest(fit_source)==discovery['source_sha256']
    fit=json.loads(fit_source.read_text())['arms']['fitted-c']['fit']
    params=np.array(fit['parameters']);coeff=np.array(fit['rf_coefficient_hz_per_ghz'])
    arrays=np.load(ROOT/'frozen'/f'{label}-observations.npz');reps=arrays['canonical_rows']
    original={r for p in discovery['proposals'] for s in p['segments'] for r in s['rows']}
    edges={};outside=set();expanded=[]
    for number,p in enumerate(discovery['proposals']):
        index=p['satellite_index'];params[6+index]=p['total_timing_s']
        pred,vis=c.predict([index],params,coeff)
        residual=circular_residual(d.measured,pred[:,0],c.prepared.alias_hz)
        vis=vis[:,0]
        outside.update(map(int,reps[vis[reps]&(np.abs(residual[reps])<=600)]))
        updated={**p,'segments':[]}
        for segment in p['segments']:
            eligible=eligible_segment_rows(segment,reps,d.times,d.receiver,d.channel,residual,vis)
            assert set(segment['rows'])<=set(eligible)
            updated['segments'].append({**segment,'eligible_rows':eligible.tolist(),
                                        'eligible_residual_native_hz':residual[eligible].tolist()})
            for row in eligible:edges.setdefault(int(row),set()).add(p['catalog_number'])
        expanded.append(updated)
        if (number+1)%200==0:print(label,'expanded',number+1,flush=True)
    matches=[]
    for group in np.unique(d.group):
        rows=np.flatnonzero(d.group==group)
        matches.extend(maximum_group_pairs({int(r):edges[int(r)] for r in rows if int(r) in edges}))
    summary=dict(scan=label,distinct_peaks=len(reps),original_proposal_rows=len(original),
                 additional_alternative_rows=len(set(edges)-original),all_segment_eligible_rows=len(edges),
                 exclusive_optimistic_bound=len(matches),exclusive_optimistic_fraction=len(matches)/len(reps),
                 no_segment_edge=len(reps)-len(edges),matches_only_outside_segment=len(outside-set(edges)),
                 no_600hz_match_to_any_current_mode=len(reps)-len(outside),elapsed_s=time.monotonic()-start,
                 scope=__doc__,source_sha256=digest(source))
    output=ROOT/'development-expanded';output.mkdir(exist_ok=True)
    (output/f'{label}-proposals.json').write_text(json.dumps({'summary':summary,'proposals':expanded},indent=2))
    (output/f'{label}-audit.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
