"""Compare fixed-site satellite choices on identical published server memberships."""
import argparse
import json
from pathlib import Path


def compare(authority, published, native):
    tracks=published['diagnostics']['track_evidence']
    sites=authority['sites'];points=native['points']
    if len(points)!=len(sites):raise ValueError('missing comparison site')
    results=[]
    priors={p['name']:p for p in published['priors']}
    for site,point in zip(sites,points):
        if len(point['tracks'])!=len(tracks):raise ValueError('missing comparison track')
        reference={t['track_id']:t for t in published['diagnostics']['selected_track_scores'][site['name']]}
        if len(reference)!=len(tracks):raise ValueError('server reference track coverage differs')
        differences=[]
        for track,actual in zip(tracks,point['tracks']):
            expected=reference[track['track_id']]
            differences.append({'track_id':track['track_id'],
                'same_satellite':str(actual['candidate_id'])==str(expected['candidate_id']),
                'same_tau':actual['tau_s']==expected['tau_s'],
                'held_delta_hz':actual['held_hz']-expected['heldout_rms_hz']})
        results.append({'site':site['name'],'track_count':len(tracks),
            'same_satellite':sum(t['same_satellite'] for t in differences),
            'same_tau':sum(t['same_tau'] for t in differences),
            'score_delta_hz':point['score_hz']-priors[site['name']]['selected']['capped_weighted_rmse_hz'],
            'max_abs_held_delta_hz':max((abs(t['held_delta_hz']) for t in differences),default=0),
            'tracks':differences})
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('authority',type=Path);p.add_argument('scores',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    read=lambda path:json.loads(path.read_text())
    result=compare(read(a.authority/'authority.json'),read(a.authority/'server-reference.json'),read(a.scores))
    with a.output.open('x') as f:f.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps([{k:v for k,v in r.items() if k!='tracks'} for r in result]))


if __name__=='__main__':main()
