"""Summarize real timing-aware candidate changes, including negative results."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent/'timing-trial'

def main():
    files=sorted(HERE.glob('*-q33.json'));summary=[];convergence=[]
    fig,axes=plt.subplots(2,2,figsize=(11,7),constrained_layout=True)
    sessions=['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3']
    for path in files:
        d=json.loads(path.read_text());sid=d['protocol']['scan'];fold=d['protocol']['fold']
        fine=json.loads(path.with_name(path.name.replace('q33','q65-b161')).read_text())
        for e in d['experiments']:
            item=dict(session_id=sid,fold=fold,kappa=e['kappa'],sigma=e['cfo_sigma_hz'],cfo_gain=e['cfo_gain'],identity_reweight_only_gain=e['identity_reweight_only_gain'],phase_gain_vs_constant=e['phase_gain_vs_constant'],maximum_probability_change=e['maximum_probability_change'],top_before=e['top_before'],top_after=e['top_after'])
            summary.append(item)
            color='tab:blue' if item['sigma']==100 else 'tab:orange';marker='o' if fold==0 else 's';x=e['kappa']+(-.04 if item['sigma']==100 else .04)
            for col,key in enumerate(['cfo_gain','phase_gain_vs_constant']):axes[sessions.index(sid),col].scatter(x,item[key],color=color,marker=marker,s=42,label=f"σ={item['sigma']} Hz, fold {fold}" if e['kappa']==.5 else None)
            if e['kappa']==1:
                other=next(r for r in fine['experiments'] if r['cfo_sigma_hz']==e['cfo_sigma_hz'])
                convergence.append(dict(session_id=sid,fold=fold,sigma=e['cfo_sigma_hz'],cfo_gain_change=other['cfo_gain']-e['cfo_gain'],phase_score_change=other['phase_gain_vs_constant']-e['phase_gain_vs_constant'],maximum_probability_change=float(np.max(abs(np.array(other['phase_updated_probabilities'])-np.array(e['phase_updated_probabilities']))))))
    for row,label in enumerate(['09:50 UTC','12:00 UTC']):
        for col,title in enumerate(['Held CFO gain after phase','Orbital phase gain over constant difference']):
            ax=axes[row,col];ax.axhline(0,color='black',lw=.7);ax.set_title(label+'\n'+title,fontsize=11);ax.set_xlabel('Illustrative phase concentration κ');ax.set_ylabel('Gain (nats)');ax.set_xticks([.5,1,2]);ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.savefig(HERE/'results.png',dpi=160);plt.close(fig)
    out=dict(rows=summary,convergence=convergence,max_abs_cfo_convergence_change=max(abs(r['cfo_gain_change']) for r in convergence),max_abs_phase_convergence_change=max(abs(r['phase_score_change']) for r in convergence))
    (HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))

if __name__=='__main__':main()
