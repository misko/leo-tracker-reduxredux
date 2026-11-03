"""Compare complete scientific observations by capture coordinates, not run IDs."""
import argparse
import csv
from pathlib import Path

from leo.native_pipeline.membership import read_observations,read_sources
from leo.native_pipeline.runner import digest,write_json


def science(path):
    obs=read_observations(path/'observations.tsv')
    read_sources(path/'candidate-map.tsv',obs)
    with (path/'observations.tsv').open() as file:
        rows={r['candidate_id']:r for r in csv.DictReader(file,delimiter='\t')}
    result={}
    with (path/'candidate-map.tsv').open() as file:
        for source in csv.DictReader(file,delimiter='\t'):
            key=tuple(int(source[k]) for k in ['visit','receiver_id','probe_index','candidate_rank'])
            if key in result:raise ValueError('duplicate source coordinate')
            row=rows[source['candidate_id']]
            result[key]=(row['source_group_id'],int(row['receiver_id']),int(row['channel']),row['edge'],
                float(row['actual_rf_hz']),*(int(row[k]) for k in ['support_start_utc_ns',
                    'support_center_utc_ns','support_end_utc_ns']),
                *(float(row[k]) for k in ['measured_cfo_hz','exact_score','control_score','margin']),
                source['epoch_kind'])
    return result


def compare(left,right):
    a,b=science(left),science(right)
    return {'left_count':len(a),'right_count':len(b),
            'missing_sources':sorted(b.keys()-a.keys()),'additional_sources':sorted(a.keys()-b.keys()),
            'changed_sources':sorted(k for k in a.keys()&b.keys() if a[k]!=b[k]),
            'all_scientific_observations_exact':a==b}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('left',type=Path)
    p.add_argument('right',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    result=compare(args.left,args.right)
    result['artifact_sha256']={side:{name:digest(path/name) for name in ['observations.tsv','candidate-map.tsv']}
        for side,path in [('left',args.left),('right',args.right)]}
    write_json(args.output,result);print(result['all_scientific_observations_exact'])
    if not result['all_scientific_observations_exact']:raise SystemExit(1)


if __name__=='__main__':main()
