"""Plot sealed fixed-probe outputs only; no geometry or likelihood evaluation."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
import numpy as np

HERE=Path(__file__).resolve().parent


def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    rf=read(HERE/'RF_seal.json')
    for path,digest in rf['files'].items():
        if sha(path)!=digest:raise ValueError('RF seal changed: '+path)
    summary=read(HERE/'summary.json');result=read(HERE/'results.json');prep=read(HERE/'preparation.json')
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    table=[];prior=[];post=[];labels=[]
    for index,case in enumerate(summary['rows']):
        for arm_index,arm in enumerate(case['arms']):
            name=arm['arm'];rows=sorted((r for r in result['rows'] if r['case']==case['case'] and r['arm']==name),key=lambda r:r['offset_km'])
            delta=np.array([r['records']['dynamic']['321']['objective']-r['records']['frozen']['321']['objective'] for r in rows])
            axes[0,index].plot([r['offset_km']*1000 for r in rows],1000*(delta-delta[2]),
                marker='o',linestyle='-' if arm_index==0 else '--',label=name)
            metadata=next(r for r in prep['rows'] if r['case']==case['case'] and r['arm']==name and r['offset_km']==0)
            label=case['case'].replace('DS24-','')+' '+name
            labels.append(label);prior.append(metadata['conditional_phase_prior_sd_s']);post.append(metadata['proposal_phase_sd_s'])
            table.append(dict(case=case['case'],norad=case['norad'],arm=name,
                central_delta_objective=arm['central_delta_objective'],
                weak_gradient_delta_per_km=arm['gradients']['321']['0.025'],
                local_weak_displacement_proxy_m=1000*arm['weak_direction_displacement_proxy_km'],
                conditional_prior_sd_s=metadata['conditional_phase_prior_sd_s'],affine_posterior_sd_s=metadata['proposal_phase_sd_s'],
                resolved=arm['qualified'],material=arm['material']))
        axes[0,index].set(title=case['case']+' / NORAD '+str(case['norad']),
            xlabel='Fixed weak-axis offset (m)',ylabel='Centered Δ(−2 log evidence) ×1000')
        axes[0,index].axhline(0,color='grey',lw=.7);axes[0,index].legend()
    axes[1,0].bar(np.arange(4),[r['local_weak_displacement_proxy_m'] for r in table],color=['#2874a6','#85c1e9','#ba4a00','#f0b27a'])
    axes[1,0].set(xticks=np.arange(4),xticklabels=labels,ylabel='Local weak-direction proxy (m)',
        title='Largest |proxy| = 0.571 m; criterion 25 m')
    axes[1,0].tick_params(axis='x',rotation=20);axes[1,0].axhline(0,color='grey',lw=.7)
    y=np.arange(4)
    axes[1,1].scatter(prior,y,marker='s',label='Frozen-Gamma prior SD')
    axes[1,1].scatter(post,y,marker='o',label='Affine posterior proposal SD')
    axes[1,1].set(xscale='log',yticks=y,yticklabels=labels,xlabel='Selected-family phase SD (s)',
        title='Integration resolves the narrower phase proposal')
    axes[1,1].legend(fontsize=8)
    axes[1,1].xaxis.set_major_locator(FixedLocator([.02,.05,.1,.2,.6]))
    axes[1,1].xaxis.set_major_formatter(FuncFormatter(lambda value,_:format(value,'.2g')))
    axes[1,1].xaxis.set_minor_locator(NullLocator())
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('Active-parent B(reference) versus B(phi): conditional effects are small\n'
                 'Same nonlinear nominal Doppler; no optimizer, accuracy estimate or global mode certificate',fontsize=13)
    fig.savefig(HERE/'coupling_diagnostic02.png',dpi=160)
    fig.savefig(HERE/'coupling_diagnostic02.pdf');plt.close(fig)
    with (HERE/'comparison02.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(table[0]),lineterminator='\n');writer.writeheader();writer.writerows(table)
    files=('report02.py','comparison02.csv','coupling_diagnostic02.png','coupling_diagnostic02.pdf','summary.json')
    with (HERE/'report_seal02.json').open('x') as stream:
        json.dump(dict(files={name:sha(HERE/name) for name in files},RF_seal_sha256=sha(HERE/'RF_seal.json')),stream,indent=2);stream.write('\n')


if __name__=='__main__':main()
