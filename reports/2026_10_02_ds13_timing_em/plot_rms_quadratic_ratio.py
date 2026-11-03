"""Plot full-fit RMS / quadratic-detrended RMS on unchanged final track rows."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'later-tle-timing-aligned-v2/receipt.json'
OUTPUT = ROOT / 'rms-quadratic-ratio'


def rms_ratio(baseline, quadratic):
    if not np.isfinite(baseline) or not np.isfinite(quadratic) or baseline < 0 or quadratic <= 0:
        raise ValueError('RMS values must be finite; denominator must be positive')
    if quadratic > baseline + 1e-9:
        raise ValueError('nested in-sample quadratic fit cannot increase RMS')
    return float(baseline / quadratic)


def track_rows(receipt):
    rows = []
    for track in receipt['tracks']:
        times = np.asarray(track['time_s'], dtype=float)
        residual = np.asarray(track['later_residual_hz'], dtype=float)
        x = (times-times.mean())/30.
        design = np.column_stack([np.ones(len(x)), x, x*x])
        coefficient, _, rank, _ = np.linalg.lstsq(design, residual, rcond=None)
        if rank != 3:
            raise ValueError('unidentifiable quadratic')
        before = float(np.sqrt(np.mean(residual**2)))
        after = float(np.sqrt(np.mean((residual-design@coefficient)**2)))
        saved = track['later_stats']
        if not np.allclose([before,after], [saved['rms_hz'],saved['quadratic_rms_hz']], rtol=1e-10, atol=1e-8):
            raise ValueError('saved RMS does not reproduce from unchanged rows')
        rows.append({'scan':track['scan'], 'catalog_number':track['catalog_number'],
                     'receiver':track['receiver'], 'length_s':float(np.ptp(times)),
                     'fit_rms_hz':before, 'fit_plus_quadratic_rms_hz':after,
                     'ratio':rms_ratio(before,after)})
    return rows


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    receipt=json.loads(SOURCE.read_text())
    rows=track_rows(receipt)
    OUTPUT.mkdir(exist_ok=False)
    fig,axes=plt.subplots(1,2,figsize=(13,7),sharex=True)
    upper=max(r['ratio'] for r in rows)+.40
    for ax,label,color in zip(axes,('A','B'),('#0072B2','#D55E00'),strict=True):
        selected=sorted((r for r in rows if r['scan']==label), key=lambda r:(-r['ratio'],r['catalog_number'],r['receiver']))
        y=np.arange(len(selected))
        ax.barh(y,[r['ratio'] for r in selected],color=color,alpha=.85,height=.66)
        ax.set_yticks(y,[f"{r['catalog_number']} / RX{r['receiver']}" for r in selected])
        for i,r in enumerate(selected):
            ax.text(r['ratio']+.045,i,f"{r['ratio']:.2f}×",va='center',fontsize=10)
        ax.axvline(1,color='#222222',linestyle='--',linewidth=1.3)
        ax.invert_yaxis();ax.set_xlim(0,upper)
        ax.set_xlabel('Fit RMS / (fit + quadratic) RMS')
        ax.set_title(f'Scan {label}',fontsize=13)
        ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('DS13 · residual RMS reduction from quadratic detrending',fontsize=16,y=.985)
    fig.text(.5,.935,'Latest archived-TLE refits · same GLRT points · tracks ranked within each scan',ha='center',fontsize=11)
    fig.text(.5,.024,'Dashed line at 1: no RMS reduction. 2× means the remaining RMS is half the original.\n'
             'Quadratic correction includes a constant and linear term; this is not the isolated benefit of curvature.\n'
             'In-sample diagnostic on previously selected points—not held-out evidence or a validated orbit correction.',
             ha='center',fontsize=9)
    fig.tight_layout(rect=(.015,.115,.985,.905),w_pad=3)
    for ext in ('png','svg'):fig.savefig(OUTPUT/f'fit-over-quadratic-rms.{ext}',dpi=180)
    plt.close(fig)
    with (OUTPUT/'ratios.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result={'source_hashes':{str(SOURCE):digest(SOURCE),str(Path(__file__)):digest(__file__)},
            'definition':'RMS of later-TLE-refitted residual / RMS after OLS constant+linear+quadratic subtraction; identical rows',
            'all_rms_recomputed_and_verified':True,'tracks':rows,
            'outputs':{str(p):digest(p) for p in OUTPUT.iterdir()}}
    (OUTPUT/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(sorted(rows,key=lambda r:-r['ratio'])[:5],indent=2))


if __name__=='__main__':run()
