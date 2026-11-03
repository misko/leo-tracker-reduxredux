"""Account for every recorded arrival and compare its detector checkpoint."""
import argparse
import json
import math
from pathlib import Path

from leo.native_pipeline.runner import digest,write_json

FIELDS=['epoch','acquired_cfo_hz','tracking_cfo_hz','exact_score','control_score','margin','glrt_complete']


def evaluate(rows,expected):
    if not rows or rows[-1].get('kind')!='summary':raise ValueError('missing terminal summary')
    summary=rows[-1];arrivals=rows[:-1]
    if len(arrivals)!=len(expected) or [r['sequence'] for r in arrivals]!=list(range(len(expected))):
        raise ValueError('missing, duplicated or reordered arrival')
    accepted=[r for r in arrivals if r['accepted']]
    rejected=len(arrivals)-len(accepted)
    failures=sum(r['status']!=0 for r in accepted)
    if (summary['arrivals'],summary['completed'],summary['failed'],summary['rejected'])!=(
            len(arrivals),len(accepted)-failures,failures,rejected):
        raise ValueError('summary disagrees with arrival accounting')
    mismatches=[]
    for row in accepted:
        if row['candidates']!=expected[row['sequence']]:mismatches.append(row['sequence'])
        if row['positive']!=sum(c[8]>=.025 for c in row['candidates']):
            raise ValueError('positive-candidate count differs')
    def stats(key,records):
        values=sorted(r[key] for r in records)
        if not values:return None
        if not all(math.isfinite(v) and v>=0 for v in values):raise ValueError('invalid timing')
        return {'mean':sum(values)/len(values),'p95':values[math.ceil(.95*len(values))-1],
                'max':values[-1]}
    result={'all_arrivals_accounted':True,'arrivals':len(arrivals),'rejected':rejected,
            'failed':failures,'candidate_mismatch_visits':mismatches,
            'scientific_match_for_all_arrivals':not rejected and not failures and not mismatches,
            'positive_candidates':sum(r['positive'] for r in accepted),
            'queue_high_water':summary['queue_high_water'],'max_rss_kib':summary['max_rss_kib'],
            'wall_ms':summary['wall_ms'],
            'producer_late_ms':stats('producer_late_ms',arrivals),'io_ms':stats('io_ms',arrivals),
            'queue_ms':stats('queue_ms',accepted),'service_ms':stats('service_ms',accepted),
            'due_to_finish_ms':stats('due_to_finish_ms',accepted),
            'scope':'Recorded IQ detector pacing only; not full pipeline or live acquisition qualification'}
    for key in ['detector_ms','projection_ms']:
        if accepted and all(key in row for row in accepted):result[key]=stats(key,accepted)
    if accepted and any(row.get('projection_ms',0)>0 for row in accepted):
        result['scope']='Recorded IQ detector plus direct projection; excludes tracking, positioning and live acquisition'
    result['quarters']=[]
    for i in range(4):
        group=arrivals[len(arrivals)*i//4:len(arrivals)*(i+1)//4]
        if not group:continue
        completed=[r for r in group if r['accepted']]
        result['quarters'].append({'first_sequence':group[0]['sequence'],'last_sequence':group[-1]['sequence'],
            'rejected':len(group)-len(completed),'producer_late_ms':stats('producer_late_ms',group),
            'queue_ms':stats('queue_ms',completed),'due_to_finish_ms':stats('due_to_finish_ms',completed)})
    return result


def load_reference(directory):
    expected=[]
    for path in sorted(directory.glob('batch-*.jsonl')):
        for line in path.read_text().splitlines():
            doc=json.loads(line)
            if 'result' not in doc:continue
            expected.append([[r['receiver_id'],r['probe_index'],rank,*[c[k] for k in FIELDS]]
                             for r in doc['result']['rows'] for rank,c in enumerate(r['candidates'])])
    if not expected:raise ValueError('empty reference')
    return expected


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();expected=load_reference(args.reference)
    result=evaluate([json.loads(l) for l in args.input.read_text().splitlines()],expected)
    result['input_sha256']=digest(args.input)
    result['reference_sha256']={p.name:digest(p) for p in sorted(args.reference.glob('batch-*.jsonl'))}
    write_json(args.output,result);print(json.dumps(result))


if __name__=='__main__':main()
