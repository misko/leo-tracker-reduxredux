"""Compare complete regional results under an explicitly supplied score policy."""
import argparse
import math
from pathlib import Path
from leo.native_pipeline.runner import digest,finite_json,write_json


def compare(actual,reference,tolerance_hz):
    if not math.isfinite(tolerance_hz) or not 0<=tolerance_hz<=1e-6:
        raise ValueError('invalid score tolerance')
    fields=('schema','evaluated_points','budget_points','deferred_cells','complete','stop_reason')
    structure=all(actual.get(k)==reference.get(k) for k in fields)
    a,b=actual['evaluations'],reference['evaluations']
    if len(a)!=actual['evaluated_points'] or len(b)!=reference['evaluated_points']:
        raise ValueError('result count disagrees with inventory')
    coordinates=len(a)==len(b)
    deltas=[]
    for left,right in zip(a,b):
        if len(left)!=3 or len(right)!=3 or not all(math.isfinite(v) for v in left+right):
            raise ValueError('invalid evaluation')
        coordinates &= left[:2]==right[:2]
        deltas.append(abs(left[2]-right[2]))
    selected=all(actual['selected'][k]==reference['selected'][k] for k in ('east_km','north_km'))
    score_a,score_b=actual['selected']['score_hz'],reference['selected']['score_hz']
    if not all(math.isfinite(v) for v in (score_a,score_b)):raise ValueError('invalid selected score')
    delta=abs(score_a-score_b)
    numerical=max([delta,*deltas],default=0)<=tolerance_hz
    full=actual['evaluated_points']==reference['evaluated_points']==400
    return {'passed':structure and coordinates and selected and numerical and full,
            'exact_json':actual==reference,'structure_exact':structure,
            'ordered_coordinates_exact':coordinates,'selected_coordinate_exact':selected,
            'maximum_score_delta_hz':max(deltas,default=0),'selected_score_delta_hz':delta,
            'absolute_score_tolerance_hz':tolerance_hz,'full_400_points':full,
            'scope':'Numerical result comparison only; search budget exhaustion is not global convergence or real-time qualification'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('actual','reference','protocol','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();protocol=finite_json(args.protocol)
    result=compare(finite_json(args.actual),finite_json(args.reference),protocol['absolute_score_tolerance_hz'])
    result['input_sha256']={str(path):digest(path) for path in (args.actual,args.reference,args.protocol)}
    write_json(args.output,result);print(result)
    if not result['passed']:raise ValueError('regional result comparison failed')


if __name__=='__main__':main()
