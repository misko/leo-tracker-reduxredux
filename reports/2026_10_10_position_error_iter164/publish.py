"""Presentation of sealed, already-evaluated193 rows; never opens references."""
import json
import math
from pathlib import Path

DATASETS=('DS16','DS17','DS18','POST18-development')
ARMS=('zero-c','fitted-c')
BRANCHES=('native','zero')


def number(value):
    return 'unavailable' if value is None else f'{value:.4f}'


def errors(value):
    return 'withheld' if value is None else ' / '.join(number(value[k]) for k in ('mean','median','p95','worst'))


def safe(value):
    if value is None:return ''
    text=value if isinstance(value,str) else json.dumps(value,sort_keys=True)
    return text.replace('|','\\|').replace('\n',' ')


def validate(summary, metrics):
    labels=[row['label'] for row in summary['rows']]
    if not summary.get('all_terminal') or len(labels)!=193 or len(set(labels))!=193:
        raise ValueError('All193 sealed rows required for publication')
    if metrics['membership']!=193 or set(labels)!={row['label'] for row in metrics['coverage']}:
        raise ValueError('Metric coverage differs from sealed summary')


def markdown(summary, metrics):
    validate(summary,metrics)
    lines=['# Full-193 single-pass discovery comparison','',
        'Consumed development data: DS16 63, DS17 51, DS18 34, and 45 newer recordings. '
        'This is the frozen single-pass native versus zero-led diagnostic, not deployed multiseparation B7 parity. '
        'Frequency fit and position accuracy are reported separately. No deployment decision is implied.','',
        '![Paired position errors](paired-position.png)','',
        '![Error distributions](error-ecdf.png)','',
        '## Position comparison','',
        'Errors are mean / median / p95 / worst in km. Full metrics are withheld when any paired endpoint is missing. '
        'Available-pair rows are explicitly descriptive subsets, never substituted full-cohort results.','',
        '| Dataset | Final arm | Pairs / members | Scope | Native errors | Zero-led errors | Regressions |',
        '|---|---|---:|---|---|---|---:|']
    for dataset in (*DATASETS,'all193'):
        for arm in ARMS:
            row=metrics['datasets'][dataset]['discovery'][arm]
            full=row['full_metrics']
            lines.append(f"| {dataset} | {arm} | {row['paired']}/{row['membership']} | Full membership | {errors(None if full is None else full['left'])} | {errors(None if full is None else full['right'])} | {row['regressions']} |")
            if not row['complete']:
                pair=row['available_pair_metrics']
                lines.append(f"| {dataset} | {arm} | {row['paired']}/{row['membership']} | Available paired subset only | {errors(pair['left'])} | {errors(pair['right'])} | {row['regressions']} |")
    lines += ['', '## Matched c comparison within each discovery policy','',
        'Positive deltas mean fitted-c has worse position error than c=0. These are matched-policy sensitivity comparisons. Selected stages and realized banks are not asserted identical, so this is not a controlled same-model likelihood contrast.','',
        '![Within-policy c comparisons](c-contrast.png)','',
        '| Dataset | Discovery | Pairs / members | Full mean delta km | Available-pair mean delta km | Regressions |',
        '|---|---|---:|---:|---:|---:|']
    for dataset in (*DATASETS,'all193'):
        for branch in BRANCHES:
            row=metrics['datasets'][dataset]['c_effect'][branch]
            delta=row['available_pair_metrics']['delta']
            lines.append(f"| {dataset} | {branch} | {row['paired']}/{row['membership']} | {number(None if row['full_metrics'] is None else row['full_metrics']['delta']['mean'])} | {number(None if delta is None else delta['mean'])} | {row['regressions']} |")
    lines += ['', '## Frequency fit, separately','',metrics['frequency_scope'],'',
        '| Dataset | Discovery | Arm | Metric | Available / members | Full mean | Available-endpoint mean |',
        '|---|---|---|---|---:|---:|---:|']
    for dataset in (*DATASETS,'all193'):
        for branch in BRANCHES:
            for arm in ARMS:
                for name,row in metrics['datasets'][dataset]['frequency'][branch][arm].items():
                    full=row['full_metrics'];available=row['available_endpoint_metrics']
                    lines.append(f"| {dataset} | {branch} | {arm} | {name} | {row['available']}/{row['membership']} | {number(None if full is None else full['mean'])} | {number(None if available is None else available['mean'])} |")
    lines += ['', '## Every member: coverage, failures and recorded cost','',
        'No endpoint fallback is authorized by this protocol. Missing endpoints remain missing. '
        'Selected stage labels below expose the inherited B7 stage-selection behavior; they do not prove every earlier stage qualified. '
        'Unknown phase durations remain unavailable, not zero. Recorded invocation time is not an embedded-speed benchmark.','',
        '![All member errors](member-errors.png)','',
        '| Member | Search / native / zero | Selected qualified / evaluated (of 4) | Selected stages | Regional coverage | Regional finals qualified / recorded | Joint qualified / recorded | Known phase seconds; unknown phases | Failures |',
        '|---|---|---|---|---|---|---|---|---|']
    coverage={r['label']:r for r in metrics['coverage']}
    for row in summary['rows']:
        cover=coverage[row['label']];endpoints=cover['endpoints']
        qualification=sum(v['qualified'] for v in endpoints.values());evaluated=sum(v['evaluated'] for v in endpoints.values())
        stages={};region_coverage={};regional_q=regional_n=joint_q=joint_n=0
        for branch in BRANCHES:
            for arm in ARMS:
                item=row.get('arms',{}).get(arm,{}).get(branch,{})
                stages[branch+'/'+arm]=item.get('selection',{}).get('accepted_stage')
            regions=row.get('regions',{}).get(branch,[])
            region_coverage[branch]=f'{len(regions)}/3 recorded; {max(0,3-len(regions))} unavailable'
            for region in regions:
                for counts in region.get('finals',{}).values():
                    regional_q+=counts.get('qualified',0);regional_n+=counts.get('attempts',0)
            for stage in row.get('joint_stages',{}).get(branch,{}).values():
                for value in stage.values():
                    if isinstance(value,bool):joint_n+=1;joint_q+=value
        durations=row.get('phase_elapsed_s',{});known=[];unknown=[]
        for phase in ('search','native','zero'):
            value=durations.get(phase)
            if value is None:unknown.append(phase)
            elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError('Invalid recorded phase duration')
            else:known.append(value)
        cost=number(math.fsum(known)) if known else 'unavailable'
        reasons=dict(row.get('failure_reasons',{}))
        for name,value in endpoints.items():
            if value.get('reason'):reasons[name]=value['reason']
        if row.get('binding_error'):reasons['binding']=row['binding_error']
        statuses=' / '.join(row.get('statuses',{}).get(p,'missing') for p in ('search','native','zero'))
        regional=f'{regional_q}/{regional_n} recorded' if regional_n else 'unavailable: no recorded attempts'
        joint=f'{joint_q}/{joint_n} recorded' if joint_n else 'unavailable: no recorded attempts'
        lines.append(f"| {row['label']} | {safe(statuses)} | {qualification} / {evaluated} | {safe(stages)} | {safe(region_coverage)} | {regional} | {joint} | {cost}; {safe(unknown)} | {safe(reasons)} |")
    lines += ['', '## Paired regressions','',
        'Positive position deltas mean zero-led is worse than native. Equality tolerance is 1e-9 km.','',
        '| Final arm | Regressing members | Members worsening more than 1 km | Maximum regression km |',
        '|---|---|---|---:|']
    for arm in ARMS:
        row=metrics['datasets']['all193']['discovery'][arm]
        lines.append(f"| {arm} | {safe(row['regression_labels'])} | {safe(row['regressions_over_1km'])} | {number(row['maximum_regression_km'])} |")
    lines += ['', 'SUMMARY.json and METRICS.json retain full evaluated coverage and paired values. '
        'Raw receipt hashes and evaluation-source authority are provided by the separately gated reporting pipeline. '
        'A hash alone is not a standalone remote replay artifact.','']
    return '\n'.join(lines)


def plots(summary, metrics, directory):
    validate(summary,metrics)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    paths=[]
    for kind in ('paired-position','error-ecdf'):
        fig,axes=plt.subplots(4,2,figsize=(11,15),squeeze=False)
        for i,dataset in enumerate(DATASETS):
            for j,arm in enumerate(ARMS):
                ax=axes[i,j];row=metrics['datasets'][dataset]['discovery'][arm];pairs=row['pairs']
                x=[p['left_km'] for p in pairs];y=[p['right_km'] for p in pairs]
                if kind=='paired-position':
                    ax.scatter(x,y,s=17,alpha=.75);limit=max([1.,*x,*y]);ax.plot([0,limit],[0,limit],color='gray',lw=.8)
                    ax.set(xlabel='Native position error (km)',ylabel='Zero-led position error (km)')
                    ax.set_xscale('symlog',linthresh=.1);ax.set_yscale('symlog',linthresh=.1)
                else:
                    for values,label in ((x,'native'),(y,'zero-led')):
                        ordered=sorted(values)
                        if ordered:ax.step(ordered,[(k+1)/len(ordered) for k in range(len(ordered))],where='post',label=label)
                    ax.set_xscale('symlog',linthresh=.1);ax.set(xlabel='Position error (km)',ylabel='Empirical cumulative fraction',ylim=(0,1.02))
                    if pairs:ax.legend()
                scope='full pairs' if row['complete'] else 'AVAILABLE PAIRS ONLY'
                ax.set_title(f'{dataset} / {arm}\n{len(pairs)}/{row["membership"]} {scope}')
                ax.grid(alpha=.2)
        fig.tight_layout();path=directory/(kind+'.png');fig.savefig(path,dpi=150);plt.close(fig);paths.append(path)
    fig,axes=plt.subplots(4,1,figsize=(14,14))
    for ax,dataset in zip(axes,DATASETS):
        rows=[r for r in summary['rows'] if r['dataset']==dataset]
        for arm,marker in (('zero-c','x'),('fitted-c','o')):
            for branch,color in (('native','tab:blue'),('zero','tab:orange')):
                points=[(i,r['arms'][arm][branch]['error_km']) for i,r in enumerate(rows)
                        if 'error_km' in r.get('arms',{}).get(arm,{}).get(branch,{})]
                ax.scatter([p[0] for p in points],[p[1] for p in points],s=15,marker=marker,color=color,label=f'{branch}/{arm}')
        ax.set_xticks(range(len(rows)),[r['label'] for r in rows],rotation=90,fontsize=6)
        ax.set_yscale('symlog',linthresh=.1);ax.set(title=dataset+' — missing endpoints are not plotted',ylabel='Position error (km)');ax.legend(fontsize=7,ncol=4);ax.grid(alpha=.2)
    fig.tight_layout();path=directory/'member-errors.png';fig.savefig(path,dpi=150);plt.close(fig);paths.append(path)
    fig,axes=plt.subplots(2,2,figsize=(12,9))
    for ax,dataset in zip(axes.flat,DATASETS):
        for branch in BRANCHES:
            row=metrics['datasets'][dataset]['c_effect'][branch];pairs=row['pairs']
            ax.scatter([p['left_km'] for p in pairs],[p['right_km'] for p in pairs],s=16,label=f'{branch}: {row["paired"]}/{row["membership"]} pairs')
        ax.axline((0,0),(1,1),color='gray',lw=.8)
        ax.set_xscale('symlog',linthresh=.1);ax.set_yscale('symlog',linthresh=.1)
        ax.set(title=dataset,xlabel='c=0 position error (km)',ylabel='Fitted-c position error (km)');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.tight_layout();path=directory/'c-contrast.png';fig.savefig(path,dpi=150);plt.close(fig);paths.append(path)
    return paths


def publish(summary, metrics, directory):
    text=markdown(summary,metrics)
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    paths=plots(summary,metrics,directory)
    (directory/'RESULTS.md').write_text(text)
    (directory/'METRICS.json').write_text(json.dumps(metrics,indent=2,allow_nan=False)+'\n')
    return paths
