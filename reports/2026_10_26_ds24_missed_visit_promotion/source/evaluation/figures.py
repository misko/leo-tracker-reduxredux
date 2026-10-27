"""Separate position/qualification, association, frequency-fit and mechanism plots."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

VARIANTS=('baseline','additions_bin_floor','additions_proxy')
LABELS={'baseline':'Baseline','additions_bin_floor':'Coherent full-bin floor','additions_proxy':'Coherent proxy'}
COLORS={'baseline':'#475569','additions_bin_floor':'#2563eb','additions_proxy':'#d97706'}


def save(fig,folder,stem):
    for suffix in ('png','pdf'):fig.savefig(folder/(stem+'.'+suffix),dpi=180,bbox_inches='tight')
    plt.close(fig)


def position_figures(rows,cases,folder,cohort='held'):
    lookup={(r['case'],r['variant'],r['arm']):r for r in rows if r['case'] in cases}
    fig,axes=plt.subplots(2,2,figsize=(12,9),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        for variant in VARIANTS:
            values=sorted(lookup[c,variant,arm]['error_m']/1000 for c in cases if lookup[c,variant,arm]['valid'])
            if values:axes[0,col].step(np.r_[0,values],np.r_[0,np.arange(1,len(values)+1)/len(cases)],where='post',color=COLORS[variant],label=f'{LABELS[variant]} ({len(values)}/{len(cases)})')
        axes[0,col].axvline(.5,color='#0f172a',ls=':',lw=1,label='500 m goal (descriptive)')
        axes[0,col].set(title=arm,ylabel='Fraction of all intended scans',xlabel='Position error (km)',ylim=(0,1.03));axes[0,col].legend(fontsize=8);axes[0,col].grid(alpha=.2)
        available=[]
        for variant,marker in [('additions_bin_floor','o'),('additions_proxy','x')]:
            for case in cases:
                b,t=lookup[case,'baseline',arm],lookup[case,variant,arm]
                if not(b['valid'] and t['valid']):continue
                x,y=b['error_m']/1000,t['error_m']/1000;available.extend([x,y]);axes[1,col].scatter(x,y,c=COLORS[variant],marker=marker,s=28)
                if variant=='additions_bin_floor':axes[1,col].annotate(case[-4:],(x,y),xytext=(3,3),textcoords='offset points',fontsize=7)
        lim=max(available,default=1)*1.06;axes[1,col].plot([0,lim],[0,lim],c='#94a3b8',lw=1)
        axes[1,col].set(xlabel='Baseline error (km)',ylabel='Treatment error (km)',xlim=(0,lim),ylim=(0,lim));axes[1,col].grid(alpha=.2)
    fig.suptitle(f'{cohort}: all-scan error CDF and complete-case paired scatter\nUnavailable scans remain in CDF denominator; scatter includes audited pairs only')
    save(fig,folder,cohort+'_error_distributions')
    fig,axes=plt.subplots(2,1,figsize=(13,7),layout='constrained',sharex=True);x=np.arange(len(cases))
    for index,arm in enumerate(('c0','fitted_c')):
        ax=axes[index]
        for j,variant in enumerate(('additions_bin_floor','additions_proxy')):
            values=[]
            for k,case in enumerate(cases):
                b,t=lookup[case,'baseline',arm],lookup[case,variant,arm]
                if b['valid'] and t['valid']:values.append(t['error_m']-b['error_m'])
                else:
                    values.append(0);ax.scatter(k+(j-.5)*.34,0,c='#dc2626',marker='x',s=40,zorder=5)
            ax.bar(x+(j-.5)*.34,values,width=.32,color=COLORS[variant],label=LABELS[variant])
        ax.axhline(0,c='#64748b',lw=1);ax.set(ylabel='Treatment − baseline (m)',title=arm);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    axes[-1].set_xticks(x,[c[-4:] for c in cases]);fig.suptitle(f'{cohort}: per-scan geographic changes\nRed x means unavailable pair; zero-height baseline-equivalent cases add no transfer evidence')
    save(fig,folder,cohort+'_paired_changes')


def association_frequency(rows,cases,folder,cohort='held'):
    lookup={(r['case'],r['variant'],r['arm']):r for r in rows if r['case'] in cases};x=np.arange(len(cases))
    fig,axes=plt.subplots(2,2,figsize=(14,8),layout='constrained',sharex=True)
    for col,arm in enumerate(('c0','fitted_c')):
        for variant in VARIANTS:
            selected=[lookup[c,variant,arm] for c in cases]
            associated=[100*r['association_fraction'] if r['valid'] else np.nan for r in selected]
            rms=[r['frequency_RMS_hz'] if r['valid'] else np.nan for r in selected]
            axes[0,col].plot(x,associated,'o-',ms=3,color=COLORS[variant],label=LABELS[variant])
            axes[1,col].plot(x,rms,'o-',ms=3,color=COLORS[variant],label=LABELS[variant])
        axes[0,col].set(title=arm,ylabel='Associated / all original-plus-added GLRT (%)');axes[1,col].set_ylabel('Reported frequency RMS (Hz)')
        for row in (0,1):axes[row,col].grid(alpha=.2);axes[row,col].legend(fontsize=8)
        axes[1,col].set_xticks(x,[c[-4:] for c in cases])
    fig.suptitle(f'{cohort}: association coverage and frequency fit are separate outcomes\nGaps are unavailable results; position accuracy is shown in separate figures')
    save(fig,folder,cohort+'_association_frequency')


def mechanisms(acquisition,rows,cases,folder,cohort='held'):
    source=[r for r in acquisition['new_native_rows'] if r['case'] in cases];byid={r['observation_id']:r for r in source}
    selected=[r for r in rows if r['case'] in cases and r['variant']=='additions_bin_floor' and r['arm']=='c0' and r['valid']]
    accepted={oid for row in selected for oid in row['added_curved_IDs']+row['added_predictive_IDs']};final=[byid[oid] for oid in accepted]
    counts=acquisition['groups'][cohort];fig,axes=plt.subplots(1,3,figsize=(15,4.6),layout='constrained')
    labels=['New native','RF graph','RF curved','Likelihood\ncurved','Likelihood\npredictive'];values=[len(source),counts['new_graph'],counts['new_curved'],sum(len(r['added_curved_IDs']) for r in selected),sum(len(r['added_predictive_IDs']) for r in selected)]
    axes[0].bar(np.arange(5),values,color=['#d97706','#7c3aed','#059669','#2563eb','#0284c7']);axes[0].set_xticks(np.arange(5),labels,rotation=15);axes[0].set_ylabel('Distinct new native owners')
    axes[0].set_title('RF and likelihood membership differ')
    for i,value in enumerate(values):axes[0].text(i,value+.5,str(value),ha='center',fontsize=8)
    bins=sorted({r['donor_count'] for r in source});x=np.arange(len(bins))
    for j,(records,label,color) in enumerate([(source,'All admitted native owners','#d97706'),(final,'New final-likelihood owners','#2563eb')]):
        axes[1].bar(x+(j-.5)*.35,[sum(r['donor_count']==b for r in records) for b in bins],width=.33,label=label,color=color)
    axes[1].set_xticks(x,bins);axes[1].set(xlabel='Earlier original donor count',ylabel='Native owners',title='Donor support');axes[1].legend(fontsize=7)
    for j,(records,label,color) in enumerate([(source,'All new native','#d97706'),(final,'Final likelihood','#2563eb')]):
        zero=sum(r['zero_fft_bin'] for r in records);fraction=zero/len(records) if records else 0
        axes[2].bar(j,fraction,color=color);axes[2].text(j,fraction+.02,f'{zero}/{len(records)}',ha='center')
    axes[2].set_xticks([0,1],['All new native','Final likelihood']);axes[2].set(ylabel='Zero residual FFT-bin fraction',ylim=(0,1.12),title='Donor-centered frequency grid')
    fig.suptitle(f'{cohort}: descriptive mechanism audit\nFinal likelihood covers {len(selected)}/{len(cases)} available primary runs; no new filter or independent-precision claim')
    save(fig,folder,cohort+'_mechanisms')
