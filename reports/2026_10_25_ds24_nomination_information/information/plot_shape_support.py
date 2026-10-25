"""Plot saved model-support metadata; no geometry, source CFO or fits."""

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    source = HERE.parent/'audit/shape_support_inventory.json'
    data = json.loads(source.read_text())
    assert data['all_metadata_checks_passed']
    cases = data['cases']; x=np.arange(len(cases))
    missing = np.array([c['without_physical_modes'] for c in cases])
    total = np.array([c['active_likelihood_families'] for c in cases])
    curved = np.array([c['curved_points_without_modes'] for c in cases])
    predictive = np.array([c['predictive_points_without_modes'] for c in cases])
    points = np.array([sum(f['curved_points']+f['predictive_points'] for f in data['families'] if f['case']==c['case']) for c in cases])
    assert (missing.sum(),total.sum(),curved.sum(),predictive.sum(),points.sum()) == (33,89,1147,397,12442)
    fig,axes=plt.subplots(1,2,figsize=(13,5.8))
    axes[0].bar(x,total-missing,label='Three-mode prior present',color='#7895ac')
    axes[0].bar(x,missing,bottom=total-missing,label='No shape-mode prior',color='#d88b42')
    for i,(m,t) in enumerate(zip(missing,total,strict=True)):
        axes[0].text(i,t+.5,f'{m}/{t} lack modes',ha='center',fontsize=9)
    axes[0].set(title='33 / 89 active scan-family instances lack shape prior',
                ylabel='Active family instances (counted separately per scan)',ylim=(0,33))
    present=points-curved-predictive
    axes[1].bar(x,present,label='Three-mode prior present',color='#7895ac')
    axes[1].bar(x,curved,bottom=present,label='No shape prior: curved likelihood',color='#d88b42')
    axes[1].bar(x,predictive,bottom=present+curved,label='No shape prior: predictive likelihood',color='#b45636')
    for i,(a,b,t) in enumerate(zip(curved,predictive,points,strict=True)):
        axes[1].text(i,t+65,f'{a+b}/{t}',ha='center',fontsize=9)
    axes[1].set(title='1,544 / 12,442 likelihood points in those families',
                ylabel='Native points in existing likelihood',ylim=(0,4700))
    for ax in axes:
        ax.set_xticks(x,[c['case'][-4:] for c in cases]);ax.set_xlabel('DS24 development case')
        ax.grid(axis='y',alpha=.2);ax.legend(loc='upper left',fontsize=8)
    fig.suptitle('Inherited shape-support rule: missing prior covariance, not a bad-identity diagnosis\nPhase, shared radio, source constants and measurement uncertainty remain',fontsize=12)
    fig.tight_layout()
    for suffix in ('png','pdf'):
        out=HERE/f'shape_support_inventory.{suffix}'
        if out.exists():raise FileExistsError(out)
        fig.savefig(out,dpi=150)
    plt.close(fig)
    files=[Path(__file__),HERE/'shape_support_inventory.png',HERE/'shape_support_inventory.pdf']
    receipt=dict(input_path=str(source),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                 scan_family_instances_without_modes=int(missing.sum()),active_scan_family_instances=int(total.sum()),
                 curved_points_without_modes=int(curved.sum()),predictive_points_without_modes=int(predictive.sum()),
                 old_likelihood_points=int(points.sum()),source_CFO_read=False,propagation_calls=0,position_fits=0,
                 no_identity_qualification=True)
    with (HERE/'shape_support_plot_seal.json').open('x') as stream:
        json.dump(receipt,stream,indent=2);stream.write('\n')


if __name__=='__main__':
    main()
