"""Require every recorded scan's scientific controls and fixed-cadence receipts."""
import argparse
import json
from pathlib import Path

from compare_projection_subset import compare_checkpoints
from compare_regional_results import compare as compare_search
from evaluate_cadence_schedule import evaluate as evaluate_schedule
from evaluate_recorded_pacing import evaluate as evaluate_detector, load_reference
from leo.native_pipeline.runner import digest, finite_json, write_json


def json_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def timing(path):
    rows=[json.loads(line) for line in path.read_text().splitlines() if line.startswith('{')]
    if not rows or rows[-1].get('scope')!='whole_process' or rows[-1].get('exit_code')!=0:
        raise ValueError('missing successful timing receipt: '+str(path))
    return rows[-1]


def evaluate_scan(directory, expected, checkpoints, seeds, tracks, host_search, arm_search, associations, tolerance):
    detector=evaluate_detector(json_lines(directory/'detector.stdout'),expected)
    checkpoint=compare_checkpoints(directory,checkpoints)
    chain=directory/'results'
    search=compare_search(finite_json(chain/'search.stdout'),finite_json(host_search),tolerance)
    exact={name:(chain/actual).read_bytes()==reference.read_bytes()
           for name,actual,reference in [('seeds','seeds.stdout',seeds),('tracks','tracks.stdout',tracks),
                                        ('arm_search','search.stdout',arm_search),
                                        ('host_associations','associations.json',associations)]}
    times={'detector':timing(directory/'detector.stderr'),'downstream':timing(directory/'downstream.stderr')}
    times.update({name:timing(chain/(name+'.stderr')) for name in ['seeds','tracks','search']})
    passed=detector['scientific_match_for_all_arrivals'] and checkpoint['complete_exact'] and search['passed'] and all(exact.values())
    return {'passed':passed,'detector':detector,'checkpoints':checkpoint,'host_search':search,
            'exact_controls':exact,'timings':times}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('report',type=Path)
    for name in ['detector-reference','checkpoint-reference','host-seeds','host-tracks','host-search','arm-search','host-associations']:
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();protocol=finite_json(a.report/'protocol.json')
    execution=finite_json(a.report/'execution.json')
    if execution.get('exit_code')!=0 or execution.get('protocol_sha256')!=digest(a.report/'protocol.json'):
        raise ValueError('unsuccessful or changed execution')
    expected=load_reference(a.detector_reference);scans=[];clocks=[]
    for i in range(len(protocol['scans'])):
        directory=a.report/f'scan-{i}'
        scans.append(evaluate_scan(directory,expected,a.checkpoint_reference,a.host_seeds,a.host_tracks,
                                   a.host_search,a.arm_search,a.host_associations,protocol['absolute_score_tolerance_hz']))
        clocks.append(next(json.loads(line) for line in (directory/'detector.stderr').read_text().splitlines()
                           if line.startswith('{') and json.loads(line).get('kind')=='replay_clock'))
    schedule=evaluate_schedule(json_lines(a.report/'controller.stdout'),clocks,
                               protocol['period_ms']*1_000_000,len(scans),protocol.get('memory_sample_ms'))
    references=[a.host_seeds,a.host_tracks,a.host_search,a.arm_search,a.host_associations,
                *sorted(a.detector_reference.glob('batch-*.jsonl')),
                a.checkpoint_reference/'observations.tsv',a.checkpoint_reference/'graph.tsv']
    result={'passed':all(s['passed'] for s in scans),'schedule':schedule,'scans':scans,
            'reference_sha256':{str(path):digest(path) for path in references},
            'evidence_sha256':{str(path.relative_to(a.report)):digest(path) for path in a.report.rglob('*')
                               if path.is_file() and (path.suffix in ('.stdout','.stderr','.tsv') or path.name in ('protocol.json','execution.json','associations.json'))},
            'scope':'Finite repeated-recording cadence and pinned numerical comparisons; native/server memberships differ; not live RF or longer-history qualification'}
    output=a.report/'evaluation.json'
    if output.exists():raise ValueError('preserve prior evaluation')
    write_json(output,result)
    print(json.dumps({'passed':result['passed'],'scans':len(scans),'schedule':schedule}))
    if not result['passed']:raise ValueError('one or more scan comparisons failed')


if __name__=='__main__':main()
