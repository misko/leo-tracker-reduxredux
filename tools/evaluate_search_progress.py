"""Verify bounded regional-search progress without treating a prefix as completion."""
import argparse
import json
import math
from pathlib import Path

from leo.native_pipeline.runner import finite_json, write_json, digest


def evaluate(rows, reference, exit_code, final=None):
    points = [r for r in rows if r.get('kind') == 'search_point']
    expected = reference['evaluations']
    if len(points)>len(expected):
        raise ValueError('extra search points')
    mismatches = []
    coordinate_mismatches = []
    score_deltas = []
    for i,(point,target) in enumerate(zip(points,expected)):
        if point['sequence'] != i:
            raise ValueError('missing, repeated or reordered sequence')
        if not math.isfinite(point['wall_s']) or point['wall_s']<0:
            raise ValueError('invalid point timing')
        if [point['east_km'],point['north_km'],point['score_hz']] != target:
            mismatches.append(i)
        if [point['east_km'],point['north_km']] != target[:2]:
            coordinate_mismatches.append(i)
        if not math.isfinite(point['score_hz']):
            raise ValueError('nonfinite point score')
        score_deltas.append(abs(point['score_hz']-target[2]))
    measured = next((r for r in reversed(rows) if r.get('scope')=='whole_process'),None)
    complete = (exit_code == 0 and len(points)==len(expected) and
                not mismatches and final==reference)
    elapsed = sum(p['wall_s'] for p in points)
    return {'completed_points':len(points),'required_points':len(expected),
            'mismatched_points':mismatches,'completed_prefix_exact':not mismatches,
            'coordinate_mismatches':coordinate_mismatches,
            'maximum_score_delta_hz':max(score_deltas,default=0),
            'full_search_qualified':complete,'exit_code':exit_code,
            'completed_point_wall_s':elapsed,'process_measurement':measured,
            'mean_completed_point_s':elapsed/len(points) if points else None,
            'scope':'Exact comparison to pinned host trace; a matching partial prefix is not a completed search'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--reference',type=Path,required=True)
    args=parser.parse_args()
    rows=[json.loads(line) for line in (args.report/'progress.jsonl').read_text().splitlines()
          if line.startswith('{')]
    execution=finite_json(args.report/'execution.json')
    path=args.report/'search.json'
    final=finite_json(path) if path.stat().st_size else None
    result=evaluate(rows,finite_json(args.reference),execution['exit_code'],final)
    result['reference_sha256']=digest(args.reference)
    result['protocol_sha256']=digest(args.report/'protocol.json')
    write_json(args.report/'evaluation.json',result)
    print(json.dumps(result))


if __name__=='__main__':main()
