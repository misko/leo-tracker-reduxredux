"""Conditional detector profiles, not two-source identifiability evidence."""
import json
import numpy as np
from benchmark import ROOT


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    folder=ROOT/'raw-peak-replay';receipt=json.loads((folder/'replay.json').read_text())
    fig,axes=plt.subplots(2,2,figsize=(11,7))
    for ax,result in zip(axes.flat,receipt['results']):
        if not result['replay_matches_persisted']:raise ValueError('Cannot plot an unreproduced detector result')
        center=float(np.mean(result['acquired_cfo_hz']));profile=result['profile']
        x=np.array([r['acquired_cfo_hz'] for r in profile])-center;y=np.array([r['exact_score'] for r in profile])
        ax.plot(x,y,'-o',ms=2,color='#333333',label='Conditional GLRT score')
        for frequency,color,label in zip(result['acquired_cfo_hz'],('#e69f00','#0072b2'),('Unassigned hypothesis','Assigned hypothesis')):
            ax.axvline(frequency-center,color=color,ls='--',label=label)
        visit,rx,probe=result['probe_key']
        ax.set_title(f"Scan {result['scan']} · visit {visit} · RX{rx}\nHypotheses {abs(np.diff(result['acquired_cfo_hz'])[0]):.2f} Hz apart")
        ax.set_xlabel('Acquired CFO relative to pair midpoint (Hz)');ax.set_ylabel('Exact-template GLRT score');ax.grid(alpha=.2)
    handles,labels=axes.flat[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.94),ncol=3,fontsize=9)
    fig.suptitle('Raw-IQ replay: nearby stored hypotheses share a broad detector response')
    fig.text(.5,.012,'Persisted scores reproduced for all four pairs. Curves hold the first hypothesis’s epoch fixed.\nSmall deterministic sample; not a one-source versus two-source test. No assignments or denominator changed.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.07,1,.87));fig.savefig(folder/'profiles.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
