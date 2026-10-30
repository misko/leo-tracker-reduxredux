"""Require physical residual checks for every fragment after group position fit."""
import argparse,hashlib
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from audit_soft_bundle_members import member_checks


def qualified(control,addition,exact,split,rows,members):
    expected={(arm,kind,m['track_id']) for arm in ('c0','fitted_c') for kind in ('nominal','continuous') for m in members}
    observed={(r['arm'],r['kind'],r['member']) for r in rows}
    return bool(control and addition and exact and split and expected==observed and len(rows)==len(expected) and all(r['passed'] for r in rows))


def run(args):
    pr=read(args.validation/'protocol.json');members=pr['target']['members'];indices=pr['target']['member_indices']
    control=read(args.trial/'control.json');addition=read(args.trial/'new_family.json');audit=read(args.trial/'exact_owner_replay.json');split=read(args.split/'result.json');rows=[]
    for r in audit['rows']:
        if r['role']!='new_family':continue
        for kind,key in [('nominal','target'),('continuous','continuous_target')]:
            for check in member_checks(r[key],indices,members):rows.append(dict(arm=r['arm'],kind=kind,**check))
    passed=qualified(control['paired_valid'],addition['paired_valid'],audit['all_verified'],split['all_support_shared'],rows,members)
    paths=[args.validation/'protocol.json',args.trial/'control.json',args.trial/'new_family.json',args.trial/'exact_owner_replay.json',args.split/'result.json']
    write(args.output,dict(rows=rows,qualified_research_candidate=passed,whole_group_qualified=control['paired_valid'] and addition['paired_valid'] and audit['all_verified'],
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},same_bundle_bias_no_member_refit=True,no_position_refit=True,no_production_change=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('validation','trial','split','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
