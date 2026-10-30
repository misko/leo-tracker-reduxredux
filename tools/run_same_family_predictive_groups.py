"""Jointly include independently validated tracks sharing a scan and satellite."""
import argparse,hashlib,sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from run_predictive_queue_inclusions import require_predictive_result
from annotation_partition_plan import require_distinct_annotation
from leo.analysis.research.grouped_prediction import identity_consensus
from test_predictive_graph_transfer import shared_family_route
from stress_joint_attachment import supervise


def build_groups(records):
    groups=defaultdict(list);seen=set()
    for row in records:
        identity=(row['job']['job_id'],row['track_id'])
        if identity in seen:raise ValueError('a curve cannot occur twice or carry competing group identities')
        seen.add(identity);groups[(row['job']['job_id'],row['norad'])].append(row)
    if any(len(v)<2 for v in groups.values()):raise ValueError('distinct multi-track groups required')
    return [dict(name=f'{key[0]}-{key[1]}',job=rows[0]['job'],norad=key[1],members=rows) for key,rows in sorted(groups.items())]


def run(args):
    if not 2<=len(args.validations)<=8:raise ValueError('two to eight validation sources required')
    records=[];hashes={}
    for folder in args.validations:
        r=read(folder/'result.json');p=read(folder/'protocol.json');require_predictive_result(r);require_distinct_annotation(r,p)
        a=identity_consensus(r['folds'],score_name='conditional_target')
        if a['status']!='conditionally_supported_identity' or shared_family_route(r['folds'],a['norad']):
            raise ValueError('this group runner requires independently supported new-family predictions')
        records.append(dict(validation=str(folder),track_id=r['track_id'],job=p['job'],norad=a['norad']))
        for f in [folder/'result.json',folder/'protocol.json']:hashes[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
    jobs=build_groups(records)
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    write(out/'protocol.json',dict(jobs=jobs,source_hashes=hashes,grouping='same immutable scan and independently validated satellite identity',
        separate_track_biases=True,one_shared_family_phase_and_orbit=True,receiver_uncertainty_integrated_once=True,
        optimizer='matched Powell for controls and additions',phase_step_s=.025,GPS_used=False,future_TLE=False,
        same_receiver_common_residual_check_required=True,
        workers=2,seconds_per_stage=600,no_production_change=True))
    def work(j):
        folder=out/j['name'];folder.mkdir();stages=[]
        def stage(name,script,options):
            cmd=[sys.executable,str(Path(__file__).with_name(script)),*options]
            result=dict(stage=name,command=cmd,**supervise(cmd,folder/(name+'.log'),600))
            write(folder/(name+'-terminal.json'),result);stages.append(result);return result['status']=='complete'
        inv=args.study/'all-large-track-recovery'/j['job']['job_id']/'inventory.json'
        ok=stage('inclusion','include_new_predictive_family.py',['--inventory',str(inv),'--validation',*[r['validation'] for r in j['members']],
            '--output',str(folder/'trial'),'--uncalibrated-label','--phase-step','0.025','--optimizer','powell'])
        if ok:ok=stage('replay','audit_predictive_family_inclusion.py',['--study',str(args.study),'--trial',str(folder/'trial'),
            '--output',str(folder/'trial/exact_owner_replay.json')])
        if ok:ok=stage('common_residual','audit_same_family_common_residual.py',['--trial',str(folder/'trial'),
            '--output',str(folder/'trial/common_residual_audit.json')])
        status='execution_failed'
        if ok:
            c=read(folder/'trial/control.json');a=read(folder/'trial/new_family.json');v=read(folder/'trial/exact_owner_replay.json')
            common=read(folder/'trial/common_residual_audit.json')
            status='RF_verified_joint_candidate' if c['paired_valid'] and a['paired_valid'] and v['all_verified'] and common['reviewed_joint_candidate'] else 'joint_inclusion_rejected'
        result=dict(job=j,stages=stages,status=status);write(out/(j['name']+'-terminal.json'),result);print(j['name'],status,flush=True);return result
    with ThreadPoolExecutor(max_workers=2) as pool:execution=list(pool.map(work,jobs))
    write(out/'execution.json',execution)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('study','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--validations',type=Path,nargs='+',required=True);run(p.parse_args())
