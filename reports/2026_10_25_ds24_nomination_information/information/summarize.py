"""Report sealed information arrays/numbers without geometry or inference."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    seal = json.loads((HERE/'scientific_seal.json').read_text())
    for path, digest in seal['files'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    data = json.loads((HERE/'results.json').read_text())
    inventory = json.loads((HERE/'inventory.json').read_text())
    cases = [row['case'] for row in inventory['cases']]
    arms = ('c0','fitted_c')
    flat, winners = [], []
    for case in cases:
        pool = [row for row in data['rows'] if row['case']==case]
        for method in ('count','duration','information'):
            row = next(q for q in pool if q.get(method+'_rank')==1)
            winners.append(dict(case=case,method=method,component=row['component'],
                candidate_norad=row['candidate_norad'],points=row['points'],span_s=row['span_s'],
                family_has_parent_likelihood=row['family_has_parent_likelihood'],
                paired_fractional_weak_variance_reduction=row['paired_ranking_score'],
                c0_fractional_weak_variance_reduction=row['arms']['c0']['fractional_weak_variance_reduction'],
                fitted_c_fractional_weak_variance_reduction=row['arms']['fitted_c']['fractional_weak_variance_reduction']))
        for row in pool:
            for arm in arms:
                a=row['arms'][arm]
                flat.append(dict(case=case,arm=arm,component=row['component'],
                    candidate_norad=row['candidate_norad'],candidate_index=row['candidate_index'],alias=row['alias'],
                    points=row['points'],span_s=row['span_s'],family_has_parent_likelihood=row['family_has_parent_likelihood'],
                    count_rank=row['count_rank'],duration_rank=row['duration_rank'],information_rank=row.get('information_rank'),
                    status=a['status'],fractional_weak_variance_reduction=a.get('fractional_weak_variance_reduction'),
                    paired_ranking_score=row.get('paired_ranking_score'),
                    baseline_weak_variance_km2=a.get('baseline_weak_variance_km2'),
                    augmented_baseline_weak_variance_km2=a.get('augmented_baseline_weak_variance_km2'),
                    logdet_gain=a.get('conditional_logdet_gain'),
                    maximum_CFO_redaction_design_difference=a.get('target_CFO_redaction_maximum_difference'),
                    reason=a.get('error','')))
    for name,rows in [('ranking.csv',flat),('winners.csv',winners)]:
        with (HERE/name).open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
            writer.writeheader();writer.writerows(rows)
    summary=dict(inventory_counts=inventory['cases'],eligible_owners=len(data['rows']),
        scored_owner_pairs=sum(q['status']=='complete' for q in data['rows']),
        blocked_owner_pairs=sum(q['status']!='complete' for q in data['rows']),
        winners=winners,rankings_disagree_cases=[c for c in cases if
            next(x for x in winners if x['case']==c and x['method']=='information')['component'] !=
            next(x for x in winners if x['case']==c and x['method']=='count')['component']],
        ranking_seconds=data['seconds'],cumulative_numerical_seconds=data['cumulative_numerical_seconds'],
        identity_qualification=False,position_fits=0,GPS_or_position_errors_used=False,
        no_source_value_use_beyond_archived_nomination='all50 successful source/arm design redaction checks exactly0',
        information_scope='conditional fixed local Gaussian mean design; no covariance derivatives or nonlinear phase integration')
    write(HERE/'summary.json',summary)
    fig,axes=plt.subplots(2,2,figsize=(12,8),squeeze=False)
    colors={'c0':'#2867a3','fitted_c':'#b95321'}
    for ax,case in zip(axes.flat,cases,strict=True):
        pool=[q for q in data['rows'] if q['case']==case and q['status']=='complete']
        for arm in arms:
            ax.scatter([q['points'] for q in pool],
                [100*q['arms'][arm]['fractional_weak_variance_reduction'] for q in pool],
                color=colors[arm],label=arm,s=35,alpha=.75)
        for method,marker,color in [('count','s','#252525'),('information','*','#c32854')]:
            q=next(q for q in pool if q.get(method+'_rank')==1)
            ax.scatter(q['points'],100*q['paired_ranking_score'],s=140 if marker=='*' else 90,
                marker=marker,facecolors='none',edgecolors=color,linewidths=1.4,label=f'{method} top1')
            ax.annotate(str(q['candidate_norad']),(q['points'],100*q['paired_ranking_score']),xytext=(5,6),textcoords='offset points',fontsize=9)
        ax.set(title=case,xlabel='Complete native owner points',ylabel='Baseline weak-direction variance reduction (%)')
        ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Same frozen owner pool: count versus local conditional information\nIdentities assumed; one-source additions; no position fit or accuracy claim',fontsize=12)
    fig.tight_layout();fig.savefig(HERE/'count_vs_information.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5),squeeze=False)
    x=np.arange(len(cases));width=.36
    for ax,arm in zip(axes.flat,arms,strict=True):
        for k,method in enumerate(('count','information')):
            values=[100*next(q for q in winners if q['case']==c and q['method']==method)[arm+'_fractional_weak_variance_reduction'] for c in cases]
            bars=ax.bar(x+(k-.5)*width,values,width,label=method)
            for bar,v in zip(bars,values,strict=True):ax.text(bar.get_x()+bar.get_width()/2,v+.3,f'{v:.2f}',ha='center',fontsize=9)
        ax.set(xticks=x,xticklabels=[c[-4:] for c in cases],title=arm,
               ylabel='Fixed baseline weak-direction variance reduction (%)',xlabel='DS24 case')
        ax.set_ylim(0,max(50,ax.get_ylim()[1]*1.1));ax.legend();ax.grid(axis='y',alpha=.2)
    fig.suptitle('Top-one allocation under identical source pool\nCount and duration select the same owner in all four scans; all winners are new families')
    fig.tight_layout();fig.savefig(HERE/'top_one_information.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,8),squeeze=False)
    for ax,case in zip(axes.flat,cases,strict=True):
        pool=[q for q in data['rows'] if q['case']==case]
        for q in pool:
            short=f"{q['candidate_norad']} ({q['points']})"
            if q['status']=='complete':
                ax.plot([0,1],[q['count_rank'],q['information_rank']],'-o',alpha=.75)
                ax.text(-.03,q['count_rank'],short,ha='right',va='center',fontsize=8)
                ax.text(1.03,q['information_rank'],short,ha='left',va='center',fontsize=8)
            else:
                ax.plot(0,q['count_rank'],'x',color='crimson',ms=8)
                ax.text(-.03,q['count_rank'],short+' blocked',ha='right',va='center',fontsize=8,color='crimson')
        ax.set(xticks=[0,1],xticklabels=['Point-count rank','Information rank'],title=case,
               xlim=(-.85,1.85),ylim=(len(pool)+.7,.3),ylabel='Rank (1 is first)')
        ax.grid(axis='y',alpha=.2)
    fig.suptitle('Every frozen owner: rank changes and explicit numerical/model nonqualification\nOne incumbent-family source lacks physical modes and remains unranked')
    fig.tight_layout();fig.savefig(HERE/'all_owner_ranks.png',dpi=150);plt.close(fig)
    outputs=['summarize.py','summary.json','ranking.csv','winners.csv','count_vs_information.png','top_one_information.png','all_owner_ranks.png']
    write(HERE/'report_seal.json',dict(files={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in outputs},
        scientific_seal_sha256=hashlib.sha256((HERE/'scientific_seal.json').read_bytes()).hexdigest(),
        source_values_or_geometry_reloaded=False,new_fits=0))


if __name__=='__main__':
    main()
