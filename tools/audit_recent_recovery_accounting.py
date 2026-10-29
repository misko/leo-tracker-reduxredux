"""Reconcile sealed recoveries by original observation ID; no position selection."""
import argparse
import hashlib
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from debug_fast_graph_unassociated import read, write
from validate_fast_target_guard import target_guard

ARMS=('c0','fitted_c')


def compare(old, new, component):
    target=next(g for g in old['gates']['tracks'] if g['component']==component)
    matches=[g for g in new['gates']['tracks'] if g['component']==component]
    ids=set(target['observation_ids'])
    now=set(new['proposed_associated_ids'])
    curved=set().union(*(set(g['observation_ids']) for g in new['gates']['tracks']))
    return dict(target_points=len(ids),target_confirmed=len(ids&now),target_in_curved_likelihood=len(ids&curved),
        same_identity=bool(matches and matches[0]['norad']==target['norad']),
        old_confirmed_points=len(old['proposed_associated_ids']),
        old_confirmed_missing=len(set(old['proposed_associated_ids'])-now),
        target_ids_sha256=hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest())


def run(args):
    study=args.study;pilot=args.pilot;out=args.output
    out.mkdir(parents=True,exist_ok=False)
    inputs={}
    def load(path):
        inputs[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return read(path)
    p=load(study/'combined-reentry/protocol.json')
    load(study/'provisional-recovery/protocol.json')
    rows=[];totals={a:dict(support_added=0,reentry_added=0,blocked_points=0,blocked_target_points=0) for a in ARMS}
    for case in sorted(p['primary_cases']+p['remaining_cases']):
        source=load(study/'combined-reentry'/case/'result.json')
        unconstrained=load(study/'combined-reentry'/case/'unconstrained.json') if source['status']=='accepted' else None
        guard=target_guard(source,unconstrained)
        original=load(study/'provisional-recovery'/case/'result.json')
        assert original['decisions']['preconstraint']==guard
        policy=source['policy'] if guard else source['support']
        support=load(study/'combined-reentry'/case/'support.json')
        row=dict(case=case,support_status=support['status'],reentry_status=source['status'],
                 guard_accepted=guard,proposal=source.get('proposal'),arms={})
        for arm in ARMS:
            base=set(source['baseline'][arm]['proposed_associated_ids']);sup=set(source['support'][arm]['proposed_associated_ids'])
            current=set(policy[arm]['proposed_associated_ids']);offered=set(source['policy'][arm]['proposed_associated_ids'])
            assert base<=sup<=current
            values=dict(support_added=len(sup-base),reentry_added=len(current-sup),blocked_points=len(offered-current),
                        blocked_target_points=source['proposal']['points'] if source['status']=='accepted' and not guard else 0)
            for k,v in values.items():totals[arm][k]+=v
            if support['status']=='accepted':
                values['support_target']=compare(source['support'][arm],policy[arm],support['component'])
                if (study/case/'result.json').exists():
                    preceding=load(study/case/'result.json')
                    values['earlier_cohort_support']=compare(preceding['support'][arm],policy[arm],support['component'])
                    assert values['earlier_cohort_support']['old_confirmed_missing']==0
            if source['status']=='accepted':values['reentry_target']=compare(source['policy'][arm],policy[arm],source['proposal']['component'])
            if case=='DS24-0089':
                manual=load(study/'priority-tracks/DS24-0089-bias-constrained'/f'{arm}.json')
                values['manual_0089']=compare(manual,policy[arm],source['proposal']['component'])
                assert values['manual_0089']['old_confirmed_missing']==0
            row['arms'][arm]=values
        rows.append(row)
    pilot_source=load(pilot/'recovery-accounting-current/result.json')
    pilot_guard=target_guard(pilot_source,load(pilot/'recovery-accounting-current/unconstrained.json') if pilot_source['status']=='accepted' else None)
    pilot_policy=pilot_source['policy'] if pilot_guard else pilot_source['support']
    manual=load(pilot/'support-backoff-final/results.json');component=manual['proposal']['component']
    catalogue=load(pilot/'recovery-accounting-current/catalogue.json')
    pilot_audit=dict(status=pilot_source['status'],guard_accepted=pilot_guard,proposal=pilot_source.get('proposal'),
        catalogue={a:{k:r[k] for k in ('norad','rms_hz','offset_hz','minimum_elevation_deg')} for a,r in catalogue.items()},arms={})
    for arm in ARMS:
        old=dict(manual['results']['restore_active_support']['arms'][arm])
        old['proposed_associated_ids']=old['associated_original_ids']
        pilot_audit['arms'][arm]=compare(old,pilot_policy[arm],component)
        pilot_audit['arms'][arm]['associated_points']=pilot_policy[arm]['proposed_associated_points']
        pilot_audit['arms'][arm]['postfit_only_points']=pilot_policy[arm]['postfit_only_points']
        assert pilot_audit['arms'][arm]['old_confirmed_missing']==0
    later=[];separate=study/'separate-fast-validation'
    for case in load(separate/'protocol.json')['cases']:
        terminal=load(separate/(case+'-terminal.json'));source=load(separate/'recovery'/case/'result.json')
        later.append(dict(case=case,status=terminal['status'],guard_accepted=terminal['guard_accepted'],
            added={a:len(set(terminal['policy'][a]['proposed_associated_ids'])-set(source['baseline'][a]['proposed_associated_ids'])) for a in ARMS}))
    write(out/'accounting.json',dict(audit_window_utc=['2026-10-29T13:11:31Z','2026-10-29T17:11:31Z'],
        source_revision=args.revision,policy='support backoff then one removed-family proposal with target gate guard; not family-witness guard',
        cohort_totals=totals,cohort=rows,pilot=pilot_audit,separate_recordings=later,
        covariance_in_current_execution_path=False,production_changed=False,
        input_sha256=inputs,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    changed=[r for r in rows if r['arms']['fitted_c']['support_added'] or r['reentry_status']=='accepted']
    fig,ax=plt.subplots(figsize=(11,6),layout='constrained')
    for i,r in enumerate(changed):
        v=r['arms']['fitted_c'];s=v['support_added'];q=v['reentry_added'];b=v['blocked_points']
        ax.barh(i,s,color='#0072b2',label='Support backoff retained' if i==0 else None)
        ax.barh(i,q,left=s,color='#009e73',label='Family reentry retained' if i==0 else None)
        ax.barh(i,b,left=s+q,color='#d55e00',hatch='//',alpha=.65,label='Earlier reentry withheld by guard' if i==0 else None)
        ax.text(s+q+b+3,i,f'{s+q} kept'+(f'; {b} withheld' if b else ''),va='center',fontsize=9)
    ax.set(yticks=range(len(changed)),yticklabels=[r['case'] for r in changed],xlabel='Additional distinct GLRT points over baseline',
           title='24-scan development audit: preserved gains and deliberate exclusions')
    ax.invert_yaxis();ax.set_xlim(0,300);ax.legend(loc='lower right',fontsize=8);ax.grid(axis='x',alpha=.2)
    fig.savefig(out/'recovery_accounting.png',dpi=170);plt.close(fig)
    print(dict(totals=totals,pilot=pilot_audit,later=later))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','pilot','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--revision',required=True);run(p.parse_args())
