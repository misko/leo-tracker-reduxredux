"""Rescore all 93 native proposals and test all newly supported hypotheses."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv,hashlib,sys
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.target_identity_evidence import evidence_ablation
from stress_joint_attachment import supervise


def prepare(args):
    rows=list(csv.DictReader(args.annotations.open()))
    if len(rows)!=93 or len({r['branch_id'] for r in rows})!=93:raise ValueError('requires complete frozen 93-proposal cohort')
    out=args.output;out.mkdir(parents=True,exist_ok=False);sources={str(args.annotations):hashlib.sha256(args.annotations.read_bytes()).hexdigest()}
    summary=[];jobs=[]
    for row in rows:
        bid=row['branch_id'];source=Path(row['source']);result=read(source/'result.json');protocol=read(source/'protocol.json')
        for path in (source/'result.json',source/'protocol.json'):sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        revised=evidence_ablation(result);original=revised['original_annotation'];joint=revised['annotation'];training=revised['training_evidence_annotation']
        if original['status']!=row['status']:raise ValueError('original annotation changed')
        target=out/bid;target.mkdir();write(target/'result.json',revised)
        write(target/'protocol.json',dict(protocol,identity_score_name='joint_target',original_annotation_source=str(source),
            original_annotation_sha256=sources[str(source/'result.json')],score_ablation_only=True,
            candidate_search_independently_validated=False,production_authorized=False))
        new=joint['status']=='conditionally_supported_identity' and original['status']!='conditionally_supported_identity'
        summary.append(dict(row,original_status=original['status'],original_norad=original['norad'],
            status=joint['status'],norad=joint['norad'],minimum_margin=joint.get('minimum_margin'),
            training_status=training['status'],training_norad=training['norad'],training_margin=training.get('minimum_margin'),
            source=str(target),newly_supported_hypothesis=new))
        if new:jobs.append(dict(branch_id=bid,scan=row['scan'],points=int(row['points']),validation=str(target),
                               inventory=str(source.parent/'protocol.json'),source=str(source),annotation=joint))
    # Inventory paths come from annotation batch job receipts, not constructed storage paths.
    for job in jobs:
        batch=read(Path(job['source']).parent/'protocol.json')
        record=next(j for j in batch['jobs'] if j['branch']['branch_id']==job['branch_id'])
        job['inventory']=record['job']['inventory']
    with (out/'annotations.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]),lineterminator='\n');w.writeheader();w.writerows(summary)
    write(out/'protocol.json',dict(jobs=jobs,all_proposals=93,source_sha256=sources,
        models=['conditional_target','joint_target','training_target'],selection='Every newly supported hypothesis; no GPS selection',
        old_status_counts=dict(Counter(r['original_status'] for r in summary)),new_status_counts=dict(Counter(r['status'] for r in summary)),
        no_production_change=True,score_rule_chosen_after_prior_case_audit=True,independent_false_association_validation=False))
    print('new hypotheses',len(jobs),dict(Counter(r['status'] for r in summary)),flush=True)


def evaluate(args):
    protocol=read(args.annotations/'protocol.json');jobs=protocol['jobs']
    if len(jobs)>24:raise ValueError('bounded hypothesis trial limited to 24 jobs')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,annotations=str(args.annotations),workers=args.workers,seconds_per_case=600,
        original_position_model=True,original_gates=True,matched_c_arms=True,GPS_used=False,
        conditional_on_exploratory_identity_score=True,no_production_change=True))
    def work(job):
        bid=job['branch_id'];cmd=[sys.executable,str(Path(__file__).with_name('include_predictive_annotations.py')),
            '--inventory',job['inventory'],'--validation',job['validation'],'--native-from-validation','--output',str(args.output/bid)]
        terminal=dict(job=job,command=cmd,**supervise(cmd,args.output/(bid+'.log'),600))
        write(args.output/(bid+'-terminal.json'),terminal);return dict(scan=job['scan'],branch_id=bid,**{k:terminal[k] for k in ('status','seconds','reason')})
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','evaluate'])
    p.add_argument('--annotations',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=8);a=p.parse_args()
    if not 1<=a.workers<=8:raise ValueError('workers must be 1..8')
    prepare(a) if a.mode=='prepare' else evaluate(a)
