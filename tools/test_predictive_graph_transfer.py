"""Bounded transfer of a frozen predictive recovery rule to specified curves."""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from debug_fast_graph_unassociated import read, write
from stress_joint_attachment import supervise
from leo.analysis.research.grouped_prediction import identity_consensus


def shared_family_route(folds,norad):
    kinds={q['arms'][arm]['prior']['kind'] for f in folds for q in f['proposals']
           if q['norad']==norad for arm in ('c0','fitted_c')}
    known={'existing_shared_posterior','new_family_causal_phase_mixture','uncalibrated_family_causal_phase_mixture'}
    if not kinds or not kinds<=known:raise ValueError('unknown or missing winning predictive prior')
    return 'existing_shared_posterior' in kinds


def run(args):
    if not 1 <= len(args.tracks) <= 4 or len(set(args.tracks)) != len(args.tracks):
        raise ValueError('one to four distinct predeclared targets required')
    queue = read(args.study/'systematic-annotation-v1'/'protocol.json')['rows']
    selected = [next(r for r in queue if r['track_id'] == t) for t in args.tracks]
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output/'protocol.json', dict(jobs=selected, workers=2, seconds_per_stage=600,
        selection=args.selection, frozen_predictive_rule=True, GPS_used=False,
        future_TLE=False, c0_vs_fitted_c=True, identity_margin=10, no_production_change=True))
    def work(job):
        root = args.output/job['track_id']; root.mkdir(); stages = []
        def stage(name, script, options):
            cmd = [sys.executable, str(Path(__file__).with_name(script)), *options]
            result = dict(stage=name, command=cmd, **supervise(cmd, root/(name+'.log'), 600))
            write(root/(name+'-terminal.json'), result); stages.append(result)
            return result['status'] == 'complete'
        ok = stage('annotation', 'annotate_predictive_only.py', [
            '--inventory', job['inventory'], '--track', job['track_id'], '--output', str(root/'annotation'),
            '--predictive-member', '--uncalibrated-phase-mixture', '--distinct-partitions'])
        if not ok: return dict(job=job, stages=stages, status='annotation_execution_failure')
        r = read(root/'annotation'/'result.json'); vote = identity_consensus(r['folds'], score_name='conditional_target')
        if vote['status'] != 'conditionally_supported_identity':
            return dict(job=job, stages=stages, status='identity_not_supported', annotation=vote)
        shared = shared_family_route(r['folds'],vote['norad'])
        ok = stage('inclusion', 'include_predictive_annotations.py' if shared else 'include_new_predictive_family.py', [
            '--inventory', job['inventory'], '--validation', str(root/'annotation'),
            '--output', str(root/'inclusion'), '--predictive-member' if shared else '--uncalibrated-label'])
        if not ok: return dict(job=job, stages=stages, status='inclusion_execution_failure', annotation=vote)
        ok = stage('replay', 'audit_shared_predictive_inclusion.py' if shared else 'audit_predictive_family_inclusion.py', [
            '--study', str(args.study), '--trial', str(root/'inclusion'),
            '--output', str(root/'inclusion'/'exact_owner_replay.json')])
        if not ok: return dict(job=job, stages=stages, status='replay_execution_failure', annotation=vote)
        passed = (read(root/'inclusion'/'control.json')['paired_valid']
                  and read(root/'inclusion'/('target_0.json' if shared else 'new_family.json'))['paired_valid']
                  and read(root/'inclusion'/'exact_owner_replay.json')['all_verified'])
        return dict(job=job, stages=stages, status='RF_verified_candidate' if passed else 'inclusion_rejected', annotation=vote)
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(work,j) for j in selected]):
            r = f.result(); results.append(r)
            write(args.output/(r['job']['track_id']+'-terminal.json'),r)
            print(r['job']['label'],r['status'],flush=True)
    write(args.output/'execution.json',results)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('study','output'): p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--tracks',nargs='+',required=True);p.add_argument('--selection',required=True)
    run(p.parse_args())
