"""Read frozen completed outputs; describe graph/native changes without inference."""
import argparse
import json
import statistics
from pathlib import Path

from report_full import ARMS, ARM_LABELS, MANIFEST, OUT, coverage, position_error, read, write_table


def stage_row(member, result, arm):
    """One descriptive within-recording stage comparison, preserving carry flags."""
    row=dict(case=member['dataset_label'],arm=arm,
             cohort='fast' if member['recording_format']=='short_window_iq_recording' else 'adaptive',
             status=result['status'],search_complete=result.get('search_complete',False),
             selected_name=result.get('ordinary_graph',{}).get('selected_name'),
             native_accepted=bool(result.get('native_accepted',False)),
             native_constrained_rescue=bool(result.get('native_constrained_rescue',False)))
    for name in ('reference','ordinary_graph','final'):
        view=result[name];fit=view['arms'][arm]
        row[name+'_error_km']=position_error(fit['endpoint_latlon'])
        row[name+'_associated_points']=coverage(view['coverage'][arm])[0]
    row['graph_changed']=not result['ordinary_graph'].get('reference_fallback',row['selected_name'] in (None,'reference'))
    for label,before,after in (('graph_minus_reference','reference','ordinary_graph'),
                               ('native_minus_graph','ordinary_graph','final'),
                               ('final_minus_reference','reference','final')):
        row[label+'_error_km']=row[after+'_error_km']-row[before+'_error_km']
        row[label+'_associated_points']=row[after+'_associated_points']-row[before+'_associated_points']
    row['native_group']='Constrained native rescue' if row['native_constrained_rescue'] else ('Ordinary native recovery' if row['native_accepted'] else 'No accepted native recovery')
    return row


def describe(rows):
    values=[r['final_error_km'] for r in rows]
    changes=[r['final_minus_reference_error_km'] for r in rows]
    return dict(n=len(rows),median_final_error_km=statistics.median(values) if values else None,
                max_final_error_km=max(values) if values else None,
                median_delta_error_km=statistics.median(changes) if changes else None,
                max_delta_error_km=max(changes) if changes else None,
                final_regressions_above_half_km=sum(v>.5 for v in changes),
                final_regressions_above_1km=sum(v>1 for v in changes),
                graph_regressions_above_half_km=sum(r['graph_minus_reference_error_km']>.5 for r in rows),
                native_regressions_above_half_km=sum(r['native_minus_graph_error_km']>.5 for r in rows))


def test_stage_arithmetic():
    """Synthetic owned test; pytest source/stage_diagnostics.py runs it explicitly."""
    from report_full import REFERENCE
    def stage(offset,count):
        return dict(arms={'c0':dict(endpoint_latlon=[REFERENCE[0]+offset,REFERENCE[1]])},
                    coverage={'c0':dict(associated=count,total_GLRT=4,accepted_observation_ids=list(range(count)))})
    result=dict(status='complete',search_complete=True,reference=stage(0,1),
                ordinary_graph=dict(stage(.01,2),selected_name='trial',reference_fallback=False),
                final=stage(.02,3),native_accepted=True)
    row=stage_row(dict(dataset_label='synthetic',recording_format='short_window_iq_recording'),result,'c0')
    assert row['graph_changed'] and row['native_group']=='Ordinary native recovery'
    assert row['graph_minus_reference_associated_points']==row['native_minus_graph_associated_points']==1
    assert abs(row['graph_minus_reference_error_km']+row['native_minus_graph_error_km']-row['final_minus_reference_error_km'])<1e-12
    assert describe([row])['n']==1 and describe([])['max_final_error_km'] is None


def figures(folder, rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    stages=(('reference','Published reference'),('ordinary_graph','Ordinary graph fit'),('final','Final after native stage'))
    for ax,arm in zip(axes,ARMS):
        top=sorted((r for r in rows if r['arm']==arm and r['final_minus_reference_error_km']>0),
                   key=lambda r:r['final_minus_reference_error_km'],reverse=True)[:10]
        for k,(stage,label) in enumerate(stages):
            ax.bar([j+(k-1)*.25 for j in range(len(top))],[r[stage+'_error_km'] for r in top],width=.24,label=label)
        ax.set_xticks(range(len(top)),[r['case'] for r in top],rotation=40,ha='right',fontsize=8)
        ax.set(ylabel='Position error (km)',title=ARM_LABELS[arm]+' · largest final regressions')
        ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
        if not top:ax.text(.5,.5,'No positive final error changes',transform=ax.transAxes,ha='center')
    fig.suptitle('Stage errors on the ten largest positive final changes per arm · GPS ranking is reporting-only')
    fig.savefig(folder/'stage_worst_regressions.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    groups=('Constrained native rescue','Ordinary native recovery','No accepted native recovery')
    for ax,arm in zip(axes,ARMS):
        for group in groups:
            values=sorted(r['final_error_km'] for r in rows if r['arm']==arm and r['native_group']==group)
            if values:ax.plot(values,[(i+1)/len(values) for i in range(len(values))],label=f'{group} (n={len(values)})')
            else:ax.plot([],[],label=group+' (n=0)')
        ax.set(xlabel='Final position error (km)',ylabel='CDF within observed group',title=ARM_LABELS[arm])
        ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Descriptive native-stage groups · unmatched selections; differences are not causal effects')
    fig.savefig(folder/'native_group_distributions.png',dpi=150);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=OUT);parser.add_argument('--manifest',type=Path,default=MANIFEST)
    args=parser.parse_args();protocol=read(args.out/'protocol.json');cases=set(protocol['cases'])
    members={m['dataset_label']:m for m in read(args.manifest)['selected']}
    results={case:read(args.out/'raw'/case/'result.json') for case in sorted(cases)}
    if any(result.get('status') in ('pending','missing') for result in results.values()):
        raise ValueError('all planned outputs must be terminal before stage diagnostics')
    rows=[stage_row(members[case],results[case],arm) for case in sorted(cases) for arm in ARMS]
    tables=args.out/'tables';plots=args.out/'figures';evidence=args.out/'evidence'
    for folder in (tables,plots,evidence):folder.mkdir(exist_ok=True)
    write_table(tables/'stage_changes.csv',rows)
    summary=[]
    for arm in ARMS:
        for cohort in ('all','fast','adaptive'):
            rr=[r for r in rows if r['arm']==arm and (cohort=='all' or r['cohort']==cohort)]
            summary.append(dict(arm=arm,cohort=cohort,group='all_deployed',**describe(rr)))
            for flag in ('graph_changed','native_accepted','native_constrained_rescue','search_complete'):
                for value in (False,True):
                    subset=[r for r in rr if r[flag]==value]
                    summary.append(dict(arm=arm,cohort=cohort,group=f'{flag}={value}',**describe(subset)))
            for name in ('Constrained native rescue','Ordinary native recovery','No accepted native recovery'):
                summary.append(dict(arm=arm,cohort=cohort,group=name,**describe([r for r in rr if r['native_group']==name])))
    record=dict(interpretation='Descriptive, unmatched stage selections; group differences are not causal effects. Inherited and execution carries remain deployed positions with search_complete=false.',
                planned_recordings=len(cases),summary=summary)
    (evidence/'stage_diagnostics.json').write_text(json.dumps(record,indent=2)+'\n')
    figures(plots,rows)


if __name__=='__main__':main()
