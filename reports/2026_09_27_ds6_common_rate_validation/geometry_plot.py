"""Illustrate training-selected geometry hypotheses and concentration limits."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from geometry import phase_evidence


def main():
    result=json.loads((HERE/'geometry-results.json').read_text())
    scans=[s for s in result['scans'] if s['evaluable']]
    fig,axes=plt.subplots(len(scans),2,figsize=(12,8),layout='constrained',squeeze=False)
    audits=[]
    for row,s in enumerate(scans):
        banks=[{k:np.array(v) for k,v in b.items()} for b in json.loads((HERE/(s['session_id']+'-geometry-banks.json')).read_text())]
        cfo_time=sum(logsumexp(b['cfo_train'],axis=-1) for b in banks)
        time_probability=np.exp(cfo_time-logsumexp(cfo_time))
        pair_scores=[]
        for b in banks:
            phase_fit=np.stack([phase_evidence(b['y'][b['mask']],sign*b['geometry'][...,b['mask']],np.ones(b['mask'].sum())) for sign in [-1,1]])
            pair_scores.append(b['cfo_train']+phase_fit)
        total=sum(logsumexp(x,axis=-1) for x in pair_scores)
        sign_index,time_index=np.unravel_index(np.argmax(total),total.shape)
        sign=[-1,1][sign_index]
        audit=dict(session_id=s['session_id'],cfo_time_posterior=time_probability.tolist(),
                   illustrative_timing_s=result['timing_s'][time_index],illustrative_baseline_sign=sign,groups=[])
        for col,(b,g,scores) in enumerate(zip(banks,s['groups'],pair_scores)):
            ids=np.array(g['shortlists']);same=(ids[0,:,:,None]==ids[1,:,None,:]).reshape(len(time_probability),-1)
            pair_probability=np.exp(b['cfo_train']-logsumexp(b['cfo_train'],axis=-1)[:,None])
            same_mass=float(np.sum(time_probability[:,None]*pair_probability*same))
            pair_index=int(np.argmax(scores[sign_index,time_index]))
            predicted=sign*b['geometry'][time_index,pair_index]
            offset=float(np.angle(np.mean(np.exp(1j*(b['y'][b['mask']]-predicted[b['mask']])))))
            prediction=np.angle(np.exp(1j*(predicted+offset)))
            flat=float(np.angle(np.mean(np.exp(1j*b['y'][b['mask']]))))
            t=np.array([o['time_s'] for o in g['observations']])
            a,c=pair_index//6,pair_index%6
            audit['groups'].append(dict(group=g['group'],cfo_same_satellite_probability=same_mass,
                illustrative_satellite_numbers=[ids[0,time_index,a].item(),ids[1,time_index,c].item()],
                cfo_max_conditional_pair_probability=float(pair_probability[time_index].max()),
                illustrative_geometric_span_deg=float(np.degrees(np.ptp(predicted)))))
            ax=axes[row,col]
            for mask,marker,label in [(b['mask'],'o','Training dwell'),(~b['mask'],'x','Held dwell')]:
                ax.scatter(t[mask],np.degrees(b['y'][mask]),marker=marker,s=65,color='tab:blue',label=label)
            ax.scatter(t,np.degrees(prediction),marker='_',s=150,color='tab:orange',label='Training-selected geometric prediction')
            ax.axhline(np.degrees(flat),color='0.5',ls='--',label='Constant response-only prediction')
            ax.set(title=f"{s['session_id'][-8:]} — CH{g['channel']} lower",xlabel='Seconds since capture start',ylabel='Wrapped double difference (degrees)',ylim=(-190,190))
            ax.legend(fontsize=8)
        audits.append(audit)
    fig.suptitle('Real phase versus candidate geometry at a CFO-derived observer\nOffset, time, sign and illustrative candidates selected from training only; no position search')
    fig.savefig(HERE/'candidate-geometry.png',dpi=160);plt.close(fig)
    (HERE/'geometry-audit.json').write_text(json.dumps(dict(scans=audits,
        caution='CFO probability concentration is conditional on a fixed 100 Hz Student-t scale and truncated catalogue hypotheses; it is not calibrated identity confidence. Geometry plots show one training-selected hypothesis; reported scores marginalize sign, time, candidates and offsets.'),indent=2)+'\n')


if __name__=='__main__':main()
