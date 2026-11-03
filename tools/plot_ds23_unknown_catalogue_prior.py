"""Separate full-factor RF-score effects from geographic effects, report only."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_unknown_catalogue_prior import OUT,ORIGINAL
from run_algo01_ds23_sample import read,sha


def main():
    decisions=read(OUT/'decisions.json');audit=read(OUT/'verification.json')
    if not audit['qualified'] or audit['decisions_sha256']!=sha(OUT/'decisions.json'):
        raise ValueError('verified category decisions required')
    evaluation=read(OUT/'evaluation.json')
    rows=[]
    for d in decisions['rows']:
        r=read(ORIGINAL/d['case']/'result.json')
        rows.append(dict(case=d['case'],conditional=max(min(t['coded_gains'].values()) for t in r['trials'][1:]),
            catalogue=max(min(t['gains'].values()) for t in d['trials'])))
    rows.sort(key=lambda r:r['catalogue'],reverse=True)
    figure,axes=plt.subplots(1,2,figsize=(17,5),gridspec_kw=dict(width_ratios=[3,1]))
    x=np.arange(len(rows));ax=axes[0]
    ax.plot(x,[r['conditional'] for r in rows],'.-',color='#71869a',label='Conditional on nominated names')
    ax.plot(x,[r['catalogue'] for r in rows],'.-',color='#b76f35',label='Normalized catalogue categories')
    ax.axhline(0,color='black',lw=.8);ax.axhline(2*np.log(2),color='gray',ls=':',label='Adoption gain threshold')
    ax.set_xticks(x,[r['case'].replace('DS23-','') for r in rows],rotation=90,fontsize=7)
    ax.set(xlabel='DS23 scan',ylabel='Best full-observation penalized RF gain\nMinimum of matched c0 and fitted-c gains',
        title='Score effect: one catalogue-aware adoption in 40 scans')
    ax.legend(fontsize=8);ax.grid(alpha=.15)
    changed=evaluation['accepted_rows'];ax=axes[1]
    if changed:
        labels=[r['case'].replace('DS23-','')+'\n'+r['arm'] for r in changed];xs=np.arange(len(changed))
        ax.bar(xs-.18,[r['incumbent_error_km'] for r in changed],width=.36,color='#71869a',label='Published incumbent')
        ax.bar(xs+.18,[r['policy_error_km'] for r in changed],width=.36,color='#b76f35',label='Unknown-category policy')
        ax.set_xticks(xs,labels)
    ax.set(ylabel='Position error (km)',title='Geographic effect of the adopted change')
    ax.legend(fontsize=8);ax.grid(axis='y',alpha=.15)
    figure.suptitle('DS23 · explicit satellite versus unknown polynomial\nSame observations, fitted endpoints and residual gates; a better score did not improve localization')
    figure.tight_layout(rect=(0,0,1,.91));figure.savefig(OUT/'score_vs_position.png',dpi=175);plt.close(figure)


if __name__=='__main__':
    main()
