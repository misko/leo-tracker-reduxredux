"""Plot five-fold decoder coverage and same-point RF residual ablations."""
import json
import numpy as np
from benchmark import ROOT,digest


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    base=json.loads((ROOT/'heldout-decoding/summary.json').read_text())
    extra_path=ROOT/'additional-comparison/heldout-decoding/summary.json'
    extra=json.loads(extra_path.read_text())
    mapping=json.loads((ROOT/'additional-comparison/frozen/manifest.json').read_text())['scans']
    cases=[(base,'A','Original A'),(base,'B','Original B'),
           (extra,'A',mapping['A']['session_id'].removeprefix('scan-fw-')),
           (extra,'B',mapping['B']['session_id'].removeprefix('scan-fw-'))]
    fig,axes=plt.subplots(2,4,figsize=(16,8),sharey='row');names=('activity','history','tracklet');x=np.arange(3)
    for col,(summary,scan,title) in enumerate(cases):
        for arm,shift,color,label in [('fitted-c',-.18,'#0072b2','Fitted c'),('zero-c',.18,'#e69f00','c = 0')]:
            vals=[next(r for r in summary['coverage'] if (r['scan'],r['method'],r['arm'])==(scan,n,arm)) for n in names]
            heights=[100*r['coherent_coverage'] for r in vals]
            bars=axes[0,col].bar(x+shift,heights,width=.35,color=color,label=label)
            axes[0,col].bar_label(bars,fmt='%.1f',fontsize=8)
            matched=[next(r for r in summary['matched_point_same_identity'] if r['scan']==scan and r['method']==n) for n in names]
            metric='fitted_rms_hz' if arm=='fitted-c' else 'zero_rms_hz'
            axes[1,col].bar(x+shift,[r[metric] for r in matched],width=.35,color=color)
        axes[0,col].axhline(90,color='#aa3333',ls='--',lw=1);axes[0,col].set_ylim(0,100)
        axes[0,col].set_title(title,fontsize=11)
        for row in range(2):
            axes[row,col].set_xticks(x,names,rotation=20);axes[row,col].grid(axis='y',alpha=.2)
    axes[0,0].set_ylabel('Coherent held-out assignments (%)')
    axes[1,0].set_ylabel('Same-point, same-identity RMS (Hz)')
    axes[0,0].legend(loc='lower left',fontsize=9)
    fig.suptitle('Four DS13 scans: five-fold decoder coverage and RF correction',fontsize=15)
    fig.text(.5,.015,'Coverage is before full identity/false-positive certification—not defensible coverage. Dashed line: 90% target.\nHeld-out decoding uses test peaks with frozen training parameters. Some calibration fits are unconverged. Shared candidate selection may favor tracklets.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.075,1,.95))
    output=ROOT/'four-scan-evaluation';output.mkdir(exist_ok=True)
    fig.savefig(output/'comparison.png',dpi=160);plt.close(fig)
    with (output/'receipt.json').open('x') as stream:
        json.dump(dict(sources={str(p):digest(p) for p in (ROOT/'heldout-decoding/summary.json',extra_path)},
                       scope=__doc__,additional_slot_mapping=mapping),stream,indent=2)


if __name__=='__main__':main()
