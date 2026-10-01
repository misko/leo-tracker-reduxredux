"""Shared, algorithm-independent scoring for the streaming research trials."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'2026_09_30_arm_curvature_tracks'
BASE=HERE.parent/'2026_09_30_arm_fast_tracks/server-baseline/output'
sys.path.insert(0,str(PREVIOUS/'evaluation'))
import compare_membership as m


def fit_quality(tracks, observations):
    """Causal eight-second linear prediction diagnostic, equal for all outputs."""
    errors=[]
    per_track=[]
    for track in tracks.values:
        points=sorted(track.points,key=lambda p:observations[p.candidate].center_ns)
        origin=min(observations[p.candidate].center_ns for p in points)
        t=np.array([(observations[p.candidate].center_ns-origin)*1e-9 for p in points])
        f=np.array([p.dealiased_cfo_hz for p in points])
        spacing=11.2e9/track.lane.rf_hz/4.4e-6
        residual=[]
        for i in range(5,len(points)):
            mask=(t[:i]>=t[i]-8)
            if sum(mask)<5 or t[i]-t[i-1]>4 or np.ptp(t[:i][mask])<2:
                continue
            coefficients=np.polyfit(t[:i][mask]-t[i],f[:i][mask],1)
            residual.append(m.circular_distance(f[i]-coefficients[1],spacing))
        errors.extend(residual)
        per_track.append({'track_index':track.index,'evaluated_predictions':len(residual),
                          'median_absolute_prediction_error_hz':float(np.median(residual)) if residual else None})
    return {'definition':'Unweighted linear fit to prior 8 s only; at least 5 prior points spanning 2 s; next gap <=4 s; circular CFO residual',
            'warning':'Diagnostic of local predictability, not identity truth; fragmentation can reduce error and predictions are correlated',
            'evaluated_predictions':len(errors),
            'median_hz':float(np.median(errors)) if errors else None,
            'p95_hz':float(np.percentile(errors,95)) if errors else None,
            'fraction_over_2500_hz':float(np.mean(np.array(errors)>2500)) if errors else None,
            'per_track':per_track}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tracks',type=Path,required=True)
    parser.add_argument('--side',choices=['arm','server'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    so=m.read_observations(BASE/'server-observations.tsv')
    obs=m.read_observations(BASE/f'{args.side}-observations.tsv')
    refs=m.read_tracks(BASE/'server-tracks.tsv',so)
    tracks=m.read_tracks(args.tracks,obs)
    settings=json.loads((PREVIOUS/'evaluation/thresholds.json').read_text())
    ss=m.read_sources(BASE/'server-candidate-map.tsv',so)
    sources=m.read_sources(BASE/f'{args.side}-candidate-map.tsv',obs)
    result=m.compare(refs,tracks,so,obs,ss,sources,settings)
    # Explicit user-approved exception; do not modify original comparator results.
    represented=set(result['primary']['reference_segments_with_any_complete_output_indexes'])-{10}
    result['reviewed']={'excluded_reference_indexes':[10],
        'reason':'User-authorized exception for likely server branch misassignment',
        'eligible_references':62,'represented_count':len(represented),
        'missing_indexes':sorted(set(range(63))-{10}-represented),
        'focus_represented':{str(i):i in represented for i in [2,19,33,35,47,59,62]},
        'warning':'Ref35 remains included; source purity can penalize valid extra detections.'}
    result['fit_quality']=fit_quality(tracks,obs)
    result['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        args.tracks,BASE/f'{args.side}-observations.tsv',BASE/'server-tracks.tsv',
        PREVIOUS/'evaluation/thresholds.json',Path(__file__)]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'side':args.side,'tracks':len(tracks.values),
        'represented_excluding_ref10':len(represented),'one_to_one_original':result['primary']['complete_one_to_one_count'],
        'prediction_p95_hz':result['fit_quality']['p95_hz']}))


if __name__=='__main__':
    main()
