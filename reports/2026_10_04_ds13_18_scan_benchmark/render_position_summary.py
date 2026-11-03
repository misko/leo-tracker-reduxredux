"""Aggregate saved independent position searches and nuisance changes.

Only completed matched Fisher-v2 baseline/percentage searches are included.
Missing cases remain missing, failures remain visible, and scans never share
position parameters. The sampling distribution is adaptive, not a posterior.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from cohort import digest
from render_positions import validate
from position_evidence import joint_stationary_at_best,eligible

HERE=Path(__file__).resolve().parent
RANKINGS=('rms','support','glrt')
FRACTIONS=(.25,.5,.75,1.)


def nuisance_delta(record,roof):
    p=np.asarray(record['parameters']);q=np.asarray(roof['parameters'])
    if p.shape!=q.shape or len(p)<7:raise ValueError('nuisance vectors must share the satellite bank')
    delta=p-q
    relative=(p[6:]-np.mean(p[6:]))-(q[6:]-np.mean(q[6:]))
    def penalty(v):
        return .5*(np.mean(v[6:])/10)**2+.5*np.sum((v[6:]-np.mean(v[6:]))**2)
    return [delta[2],delta[4],delta[3],delta[5],record['coefficient']-roof['coefficient'],
            float(np.mean(delta[6:])),float(np.sqrt(np.mean(relative**2))),float(penalty(p)-penalty(q))]


def case_path(directory,ranking,fraction):
    relative=Path('selection-p10-g600-t1')/f'alternatives-{"support" if fraction==1. else ranking}-{int(fraction*100)}'/'summary.json'
    clean=directory/'position-fisher-v2'/relative
    warning=directory/'position-fisher-v2-calibration-warning'/relative
    return warning if not clean.exists() and warning.exists() else clean


def run(inputs,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cohort=json.loads((HERE/'cohort-v2.json').read_text())
    rows=[];sources={};baseline={};subsets={};verified={}
    for scan in cohort['scans']:
        label=scan['label'];directory=inputs/label/'seed-timing-v6'
        if scan['split']=='locked_test' and not (HERE/'final-settings.json').exists():continue
        for ranking in RANKINGS:
            for fraction in FRACTIONS:
                path=case_path(directory,ranking,fraction)
                if not path.exists():continue
                case=validate(json.loads(path.read_text()))
                for source,expected in case['signature']['inputs']['sources'].items():
                    if source not in verified:verified[source]=digest(Path(source).read_bytes())
                    if verified[source]!=expected:raise ValueError('stale position summary input')
                sources[str(path)]=digest(path.read_bytes());subsets[label,ranking,fraction]=case
                if fraction==1. and ranking!='support':continue
                for arm,result in case['arms'].items():
                    best=result['best_found'];roof=result['roof']
                    rows.append(dict(scan=label,split=scan['split'],ranking=ranking,fraction=fraction,arm=arm,
                                     retained_windows=case['signature']['inputs']['retained_windows'],
                                     error_m=result['radius_m'],boundary=result['boundary'],ambiguous=result['ambiguous'],
                                     joint_stationary=joint_stationary_at_best(result),roof_converged=roof['success'],
                                     eligible=eligible(result,case['signature']['inputs']),
                                     calibration_warning=bool(case['signature']['inputs'].get('calibration_warnings')),
                                     score_change=best['objective']-roof['objective'],
                                     gradient_east_per100m=roof['position_gradient_per_km'][0]/10,
                                     gradient_north_per100m=roof['position_gradient_per_km'][1]/10,
                                     failed_fits=sum(not r['success'] for r in result['records'])))
                if fraction==1.:baseline[label]=case
    output.mkdir(exist_ok=True,parents=True)
    if not rows:return
    with (output/'position-summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (output/'position-summary.json').write_text(json.dumps(dict(scope=__doc__,sources=sources,rows=rows),indent=2,allow_nan=False))
    # Per-scan subset curves use the same axes and exact definitions as A/B.
    for label in sorted({key[0] for key in subsets}):
        available=sum((label,r,f) in subsets for r in RANKINGS for f in FRACTIONS)
        if available<=3:continue
        fig,axes=plt.subplots(1,3,figsize=(15,5),sharey=True)
        for ax,ranking,title in zip(axes,RANKINGS,('Lowest satellite RMS (roof oracle)','Most windows per satellite','Highest refined window GLRT score')):
            for arm,color in (('fitted-c','#0072b2'),('zero-c','#d55e00')):
                values=[]
                for fraction in FRACTIONS:
                    case=subsets.get((label,ranking,fraction));result=case['arms'][arm] if case else None
                    values.append(result['radius_m'] if result else np.nan)
                    if result:
                        marker='^' if result['boundary'] else '*' if result['ambiguous'] else 'o'
                        ax.scatter(fraction*100,result['radius_m'],marker=marker,s=95 if marker!='o' else 35,color=color,zorder=3)
                        if not eligible(result,case['signature']['inputs']):ax.plot(fraction*100,result['radius_m'],'kx',ms=11,zorder=4)
                        ax.annotate(f'{result["radius_m"]:.0f}',(fraction*100,result['radius_m']),xytext=(0,8 if arm=='zero-c' else -17),textcoords='offset points',ha='center',fontsize=8,color=color)
                ax.plot(np.array(FRACTIONS)*100,values,color=color,label=arm)
            ax.set(title=title,xticks=[25,50,75,100],xlabel='Top fraction retained (%)',ylim=(-80,2180))
            ax.axhline(2000,ls=':',color='#777777');ax.grid(alpha=.15);ax.legend()
        axes[0].set_ylabel('Best-found distance from roof (m)')
        fig.suptitle(f'{label} · independent 2 km subset searches · {available}/12 plotted cells available',fontsize=15)
        fig.text(.5,.01,'Missing runs are gaps, not zero error. The identical 100% case is shared across all three rankings.\nTriangle = boundary; star = restart ambiguity; cross = ineligible convergence/calibration/boundary result. Fixed roof-conditioned memberships.',ha='center',fontsize=10)
        fig.tight_layout(rect=(0,.11,1,.92));fig.savefig(output/f'{label}-subsets.png',dpi=150);plt.close(fig)
    # Nuisance panels use only the baseline full set, avoiding mixtures of
    # parameter dimensionality or priors in a single scan's delta reference.
    if baseline:
        fig,axes=plt.subplots(2,4,figsize=(16,8))
        labels=('Δ RX0 offset (Hz)','Δ RX1 offset (Hz)','Δ RX0 drift (Hz/s)','Δ RX1 drift (Hz/s)',
                'Δ RF coefficient (Hz/GHz)','Δ common timing (s)','RMS Δ satellite-relative timing (s)','Δ timing prior penalty (NLL)')
        colors=plt.get_cmap('tab20')
        for index,(label,case) in enumerate(baseline.items()):
            color=colors(index%20)
            for arm in ('fitted-c','zero-c'):
                result=case['arms'][arm];roof=result['roof'];best=result['best_found']
                seen=set()
                for record in result['records']:
                    key=(tuple(np.round(record['point_km'],6)),round(record['objective'],6))
                    if key in seen:continue
                    seen.add(key);delta=nuisance_delta(record,roof);error=1000*np.linalg.norm(record['point_km'])
                    for ax,value in zip(axes.ravel(),delta):
                        ax.scatter(error,value,s=9,alpha=.18,color=color,marker='o' if record['success'] else 'x')
                for ax,value in zip(axes.ravel(),nuisance_delta(best,roof)):
                    ax.scatter(result['radius_m'],value,s=55,c=[color],edgecolors='black',marker='o' if arm=='fitted-c' else 's',label=label if arm=='fitted-c' else None)
        for ax,label in zip(axes.ravel(),labels):
            ax.set(xlabel='Position distance from roof (m)',ylabel=label);ax.axhline(0,color='#777777',lw=.8);ax.grid(alpha=.15)
        handles,names=axes[0,0].get_legend_handles_labels()
        fig.legend(handles,names,loc='upper center',bbox_to_anchor=(.5,.95),ncol=min(9,len(names)),fontsize=9)
        fig.suptitle(f'{len(baseline)} completed scans · nuisance changes from each same-model roof fit',fontsize=15)
        fig.text(.5,.015,'Faint points: saved adaptive fits, not posterior draws; crosses did not converge. Large markers: lowest saved score.\nCircle = fitted c; square = c=0. Each scan and RF arm has its own roof reference. Correlation does not establish causation.',ha='center',fontsize=10)
        fig.tight_layout(rect=(0,.10,1,.87));fig.savefig(output/'nuisance-vs-position.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path);p.add_argument('--output',type=Path,default=HERE/'position-summary')
    a=p.parse_args();run(a.inputs,a.output)
