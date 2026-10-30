"""Separate a tested target from unscored automatic extension discoveries."""
import argparse,hashlib
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context


def scoped_membership(before,after,target,fitted,owners_before,owners_after):
    before,after,target,fitted=map(set,(before,after,target,fitted))
    if before&target:raise ValueError('target already belongs to control')
    if not before<=after or not target<=after:raise ValueError('lost incumbent or missing target')
    if any(owners_after.get(o)!=n for o,n in owners_before.items()):raise ValueError('incumbent owner changed')
    incidental=after-before-target
    if incidental&fitted:raise ValueError('incidental extension entered the fitted observations')
    return dict(reviewed_associated_ids=sorted(before|target),incidental_unvalidated_ids=sorted(incidental),
                added_validated_target_ids=sorted(target),raw_proposed_count=len(after),reviewed_proposed_count=len(before|target))


def run(args):
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sources={}
    def load(path):sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return read(path)
    pr=load(args.trial/'protocol.json');control=load(args.trial/'control.json');addition=load(args.trial/'new_family.json');audit=load(args.trial/'exact_owner_replay.json')
    if not(control['paired_valid'] and addition['paired_valid'] and audit['all_verified']):raise ValueError('scope projection requires otherwise-qualified RF trial')
    inv=load(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv)
    if any(pr.get(k) for k in ('inactive_fragment_sources','graph_bundle_sources','measurement_refinements')):raise ValueError('native unchanged-target trial required')
    targets={o for t in pr['targets'] for o in t['observation_ids']};rows={}
    for arm,(p,x) in d['problems'].items():
        fitted={o for i,sl in zip(p.members,p.slices,strict=True) for o,k in zip(d['scan'].tracks[i]['observation_ids'],d['keep'][sl],strict=True) if k}
        fitted.update(o for e in d['entries'] for o in e['observation_ids']);fitted.update(targets)
        c=next(r for r in audit['rows'] if r['role']=='control' and r['arm']==arm);a=next(r for r in audit['rows'] if r['role']=='new_family' and r['arm']==arm)
        for target in pr['targets']:
            if any(a['owners'].get(o)!=target['norad'] for o in target['observation_ids']):raise ValueError('target owner differs from annotation')
        rows[arm]=scoped_membership(control['arms'][arm]['proposed_associated_ids'],addition['arms'][arm]['proposed_associated_ids'],targets,fitted,c['owners'],a['owners'])
        extras=set(rows[arm]['incidental_unvalidated_ids']);rows[arm]['incidental_tracks']=[dict(component=t['key'],observation_ids=sorted(extras&set(t['observation_ids']))) for t in d['scan'].tracks if extras&set(t['observation_ids'])]
    write(args.output,dict(job=pr['job'],arms=rows,source_hashes=sources,scope='control membership plus separately validated target only',
        incidental_extensions_enter_position_objective=False,position_or_measurements_changed=False,incidental_points_rejected=False,
        incidental_points_require_separate_annotation=True,RF_qualified_target_only=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','trial','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
