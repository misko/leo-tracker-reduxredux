"""Readable reporting revision, fixed alias zero; saved-array arithmetic only."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

HERE=Path(__file__).resolve().parent
RUN=HERE/'run02'
ARMS=('c0','fitted_c')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    seal=read(RUN/'RF_seal.json')
    for path,h in seal['files'].items():
        if sha(path)!=h:raise ValueError('RF artifact changed: '+path)
    summary=read(HERE/'report02/summary.json');records=summary['rows']
    evidence,axes=plt.subplots(1,2,figsize=(12,4.5),squeeze=False)
    cfo,cfoaxes=plt.subplots(2,2,figsize=(12,7),squeeze=False)
    residual,resaxes=plt.subplots(2,2,figsize=(12,7),squeeze=False)
    table=[]
    for col,arm in enumerate(ARMS):
        directory=RUN/arm
        with np.load(directory/'Dposterior_GL64.npz') as saved:
            prediction=saved['prediction_mean_Hz'];sd=saved['prediction_SD_Hz']
        with np.load(directory/'joint_background.npz') as saved:
            raw=saved['raw_hz'];times=saved['times_s'];ids=saved['native_ids']
        for row,label in enumerate(('CH3','CH4')):
            ix=slice(57,81) if label=='CH3' else slice(81,124)
            px=slice(0,24) if label=='CH3' else slice(24,67)
            t,y,mu,s=times[ix],raw[ix],prediction[px],sd[px]
            ax=cfoaxes[row,col]
            ax.fill_between(t,(mu-2*s)/1000,(mu+2*s)/1000,color='#5c8db7',alpha=.25,label='D-only moment ±2 SD')
            ax.plot(t,mu/1000,color='#22658e',label='D-only predictive mean')
            ax.plot(t,y/1000,'k.-',ms=4,lw=1,label='Observed W, fixed alias 0')
            ax.set_title(label+' / '+arm);ax.set_ylabel('Radio-conditioned CFO (kHz)');ax.set_xlabel('Scan time (s)')
            ax.legend(fontsize=7);ax.grid(alpha=.2)
            rx=resaxes[row,col]
            rx.fill_between(t,-2*s,2*s,color='#5c8db7',alpha=.25,label='D-only moment ±2 SD')
            rx.plot(t,y-mu,'k.-',ms=4,lw=1,label='Observed − predicted, fixed alias 0')
            rx.axhline(0,color='#22658e',lw=.7)
            rx.set_title(label+' / '+arm);rx.set_ylabel('Residual (Hz)');rx.set_xlabel('Scan time (s)')
            rx.legend(fontsize=7);rx.grid(alpha=.2)
            for oid,tm,observed,mean,sigma in zip(ids[ix],t,y,mu,s,strict=True):
                table.append(dict(arm=arm,witness=label,native_id=str(oid),time_s=float(tm),fixed_alias=0,
                    radio_conditioned_CFO_Hz=float(observed),D_only_prediction_Hz=float(mean),D_only_prediction_SD_Hz=float(sigma),
                    residual_Hz=float(observed-mean),W_response_used_in_prediction=False))
            record=next(r for r in records if r['arm']==arm and r['witness']==label)
            ex=axes[0,row]
            d=record['discovery_objective']
            same=record['joint_same_objective'];partial=record['same_nonterminal_primary_objective'];mixed=record['joint_mixed_objective']
            ex.plot(col*3,(same if same is not None else partial)-d,'o',ms=7,
                markerfacecolor='#22658e' if same is not None else 'none',markeredgecolor='#22658e')
            ex.plot(col*3+1,mixed-d,'o',ms=7,color='#b9563b')
            resultpath=directory/(label+'_result.json')
            if resultpath.exists():
                comparison=read(resultpath)['comparison']
                for offset,model in enumerate(('same','mixed')):
                    bounds=comparison[model+'_conditional_log_evidence_bounds']
                    ex.vlines(col*3+offset,-2*bounds[1],-2*bounds[0],color='black',lw=2)
    for row,label in enumerate(('CH3','CH4')):
        for grid in (cfoaxes,resaxes):
            limits=[ax.get_ylim() for ax in grid[row]]
            low=min(x[0] for x in limits);high=max(x[1] for x in limits)
            for ax in grid[row]:ax.set_ylim(low,high)
        ex=axes[0,row]
        status='unresolved W in both c arms' if label=='CH3' else 'budget-limited; pair unqualified'
        ex.set_title(label+': '+status,fontsize=11,pad=12)
        ex.set_xticks([0,1,3,4],['c0 shared','c0 W null','fit shared','fit W null'],rotation=25)
        ex.set_ylabel('−2 log conditional evidence');ex.set_yscale('symlog',linthresh=1.);ex.grid(alpha=.2)
        handles=[Line2D([],[],marker='o',color='none',markerfacecolor='#22658e',markeredgecolor='#22658e',label='Shared 57450'),
            Line2D([],[],marker='o',color='none',markerfacecolor='#b9563b',markeredgecolor='#b9563b',label='Physical D / polynomial W')]
        if label=='CH4':handles.append(Line2D([],[],marker='o',color='none',markerfacecolor='none',markeredgecolor='#22658e',label='Nonterminal primary checkpoint'))
        ex.legend(handles=handles,loc='center',bbox_to_anchor=(.53,.72),fontsize=8,framealpha=.9)
    evidence.suptitle('Shared 57450 versus physical D / polynomial W\nCommon D denominator; the overlapping witness comparisons are not summed',fontsize=12)
    evidence.tight_layout(rect=(0,0,1,.9));evidence.savefig(HERE/'conditional_evidence03.png',dpi=160);plt.close(evidence)
    for figure,name,title in ((cfo,'fixed_alias0_CFO03.png','Complete witnesses versus CH5-only 57450 prediction'),
        (residual,'fixed_alias0_residual03.png','Complete-witness residuals from CH5-only 57450 prediction')):
        figure.suptitle(title+'\nFixed alias 0 in inherited graph gauge, not selected from W; moment bands are not calibrated coverage',fontsize=11)
        figure.tight_layout(rect=(0,0,1,.92));figure.savefig(HERE/name,dpi=160);plt.close(figure)
    with (HERE/'fixed_alias0_residuals03.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    files=['plot03.py','conditional_evidence03.png','fixed_alias0_CFO03.png','fixed_alias0_residual03.png','fixed_alias0_residuals03.csv']
    seal=dict(files={name:sha(HERE/name) for name in files},source_RF_seal_sha256=sha(RUN/'RF_seal.json'),
        report02_seal_sha256=sha(HERE/'report02/report_seal.json'),new_propagation=0,new_scores=0,position_fits=0,GPS_used=False,
        revision='readability and root-requested fixed-alias0 overlays; no selected W alias or upgraded CH4 comparison')
    with (HERE/'plot03_seal.json').open('x') as stream:json.dump(seal,stream,indent=2);stream.write('\n')
    print('saved plots03 and all134 matched-arm native witness rows')


if __name__=='__main__':main()
