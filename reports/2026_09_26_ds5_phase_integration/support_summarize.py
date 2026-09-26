from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from support_calibration import predict

HERE=Path(__file__).resolve().parent/'support-trial'

def main():
    fig,axes=plt.subplots(2,2,figsize=(11,7),constrained_layout=True);summary=[]
    for row,sid in enumerate(['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3']):
        d=json.loads((HERE/(sid+'.json')).read_text());p=d['protocol'];cal=p['calibration'];target=[r for r in p['source_rows'] if r['session_id']==sid]
        ax=axes[row,0];ax.scatter([r['feature'] for r in target],np.degrees([abs(r['error_rad']) for r in target]),s=20,label='Unseen-scan dwell agreement')
        ax.set_xlabel('Training-pilot support feature');ax.set_ylabel('|Held−train DD phase| (deg)');ax.set_title(['09:50 UTC','12:00 UTC'][row]+' — internal consistency',fontsize=11);ax.grid(alpha=.2)
        right=ax.twinx();x=np.linspace(0,.5,100);right.plot(x,predict(cal['parameters'],x),color='tab:orange');right.set_ylabel('κ fitted on other scans',color='tab:orange');right.set_ylim(0,9)
        ax=axes[row,1]
        for offset,arm,color in [(-.2,'fixed_one','gray'),(0,'development_constant','tab:blue'),(.2,'support_calibrated','tab:orange')]:
            values=[next(e['cfo_gain'] for e in d['experiments'] if e['fold']==fold and e['sigma']==sigma and e['arm']==arm) for sigma,fold in [(100,0),(100,1),(200,0),(200,1)]]
            ax.bar(np.arange(4)+offset,values,width=.2,label=arm.replace('_',' '),color=color)
        ax.axhline(0,color='black',lw=.7);ax.set_xticks(range(4),['100 / f0','100 / f1','200 / f0','200 / f1']);ax.set_xlabel('CFO σ (Hz) / whole-dwell fold');ax.set_ylabel('Held CFO gain over CFO-only (nats)');ax.legend(fontsize=7);ax.set_title('Association benefit remains model-dependent',fontsize=11)
        summary.append(dict(session_id=sid,calibration=cal,validation=p['validation'],experiments=[{k:e[k] for k in ('fold','sigma','arm','cfo_gain','phase_gain_vs_constant','maximum_probability_change','top_before','top_after')} for e in d['experiments']]))
    fig.savefig(HERE/'results.png',dpi=160);plt.close(fig)
    (HERE/'summary.json').write_text(json.dumps(dict(scans=summary),indent=2)+'\n')

if __name__=='__main__':main()
