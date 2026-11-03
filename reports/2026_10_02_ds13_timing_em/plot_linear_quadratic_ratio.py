"""Incremental in-sample RMS benefit of a quadratic over a linear correction."""
import csv
import json
from pathlib import Path

import numpy as np

from plot_rms_quadratic_ratio import ROOT, SOURCE, digest, rms_ratio, track_rows

OUTPUT = ROOT / 'rms-linear-quadratic-ratio'


def linear_quadratic_rows(receipt):
    rows = track_rows(receipt)  # Independently verifies baseline and quadratic RMS.
    lookup = {(t['scan'],t['catalog_number'],t['receiver']):t for t in receipt['tracks']}
    for row in rows:
        track = lookup[(row['scan'],row['catalog_number'],row['receiver'])]
        t = np.asarray(track['time_s'],float)
        y = np.asarray(track['later_residual_hz'],float)
        design = np.column_stack([np.ones(len(t)),(t-t.mean())/30.])
        coefficient,_,rank,_ = np.linalg.lstsq(design,y,rcond=None)
        if rank != 2:
            raise ValueError('unidentifiable linear fit')
        linear = float(np.sqrt(np.mean((y-design@coefficient)**2)))
        if not np.isclose(linear,track['later_stats']['line_rms_hz'],rtol=1e-10,atol=1e-8):
            raise ValueError('saved linear RMS does not reproduce')
        row['fit_plus_linear_rms_hz'] = linear
        row['ratio'] = rms_ratio(linear,row['fit_plus_quadratic_rms_hz'])
    return rows


def run():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = linear_quadratic_rows(json.loads(SOURCE.read_text()))
    OUTPUT.mkdir(exist_ok=False)
    fig,axes = plt.subplots(1,2,figsize=(13,7),sharex=True)
    upper = max(r['ratio'] for r in rows)+.17
    for ax,label,color in zip(axes,('A','B'),('#0072B2','#D55E00'),strict=True):
        selected = sorted((r for r in rows if r['scan']==label),
                          key=lambda r:(-r['ratio'],r['catalog_number'],r['receiver']))
        y = np.arange(len(selected))
        ax.barh(y,[r['ratio'] for r in selected],color=color,alpha=.85,height=.66)
        ax.set_yticks(y,[f"{r['catalog_number']} / RX{r['receiver']}" for r in selected])
        for i,row in enumerate(selected):
            ax.text(row['ratio']+.015,i,f"{row['ratio']:.3f}×",va='center',fontsize=10)
        ax.axvline(1,color='#222222',linestyle='--',linewidth=1.3)
        ax.invert_yaxis();ax.set_xlim(0,upper)
        ax.set_xlabel('(Fit + linear) RMS / (fit + quadratic) RMS')
        ax.set_title(f'Scan {label}',fontsize=13)
        ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('DS13 · additional RMS reduction from curvature',fontsize=16,y=.985)
    fig.text(.5,.935,'Latest archived-TLE refits · identical GLRT points · tracks ranked within each scan',ha='center',fontsize=11)
    fig.text(.5,.024,'Dashed line at 1: quadratic adds no improvement over the linear fit.\n'
             'Both fits include a constant and linear term; the denominator additionally fits a quadratic term.\n'
             'In-sample, pooled-channel diagnostic—not held-out evidence or a validated physical correction.',
             ha='center',fontsize=9)
    fig.tight_layout(rect=(.015,.115,.985,.905),w_pad=3)
    for ext in ('png','svg'):
        fig.savefig(OUTPUT/f'linear-over-quadratic-rms.{ext}',dpi=180)
    plt.close(fig)
    with (OUTPUT/'ratios.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    sources=[SOURCE,Path(__file__),ROOT/'plot_rms_quadratic_ratio.py']
    receipt={'source_hashes':{str(p):digest(p) for p in sources},
             'definition':'OLS linear-detrended RMS / OLS quadratic-detrended RMS, identical final rows and latest TLE refits',
             'all_rms_recomputed_and_verified':True,'tracks':rows,
             'outputs':{str(p):digest(p) for p in OUTPUT.iterdir()}}
    (OUTPUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    for r in sorted(rows,key=lambda r:-r['ratio'])[:5]:
        print(r['scan'],r['catalog_number'],r['receiver'],r['ratio'])


if __name__=='__main__':run()
