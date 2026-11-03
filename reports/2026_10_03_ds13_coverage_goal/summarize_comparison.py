"""Summarize saved matched development runs without claiming validation."""
import csv,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from benchmark import ROOT


def main():
    folder=ROOT/'development-comparison';rows=[]
    for scan in ('A','B'):
        for method in ('activity','history','tracklet'):
            result=json.loads((folder/f'{scan}-{method}.json').read_text())
            residual=[r['residual_native_hz'] for r in result['records'] if r['identity_screen_pass']]
            rows.append({k:result[k] for k in ('scan','method','candidate_count','denominator',
                'raw_assigned','coherent_assigned','identity_screen_assigned','raw_coverage',
                'screened_coverage','decoding_s')})
            rows[-1]['screened_native_rms_hz']=float(np.sqrt(np.mean(np.square(residual)))) if residual else None
    with (folder/'summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
    for ax,scan in zip(axes,('A','B')):
        values=[r for r in rows if r['scan']==scan];x=np.arange(3)
        for dx,field,label,color in [(-.25,'raw_assigned','Raw assignments','#bbb'),
                (0,'coherent_assigned','Coherent','#56a1cc'),(.25,'identity_screen_assigned','Identity screen','#0072b2')]:
            heights=[100*r[field]/r['denominator'] for r in values]
            bars=ax.bar(x+dx,heights,.24,label=label,color=color)
            ax.bar_label(bars,fmt='%.1f',fontsize=8)
        ax.axhline(90,color='#d55e00',ls='--',label='90% target')
        ax.set(xticks=x,xticklabels=['Activity','History/MHT','Tracklet'],ylim=(0,100),title=f'Scan {scan}')
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axes[0].set_ylabel('Frozen-denominator coverage (%)');axes[1].legend(loc='lower right')
    fig.suptitle('DS13 expanded-bank decoder comparison — development only')
    fig.text(.5,.02,'Full-data calibration and shared fixed timing modes. Identity screening is preliminary.\nNo held-out or negative-control validation; these percentages are not certified defensible coverage.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.1,1,.95));fig.savefig(folder/'coverage.png',dpi=160);plt.close(fig)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
