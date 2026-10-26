"""Equal-scale display of saved, sealed precision-block displacements only."""
from pathlib import Path
import hashlib
import json
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'mechanism/rf_report/summary.json'
OUT = ROOT/'figures'


def main():
    start = time.monotonic()
    data = json.loads(SOURCE.read_text())
    OUT.mkdir(exist_ok=False)
    fig, axes = plt.subplots(2, 2, figsize=(10.4, 10.4), layout='constrained')
    colors = {'00':'.35', '10':'#176b8b', '01':'#b06624', '11':'#714d86'}
    offsets = {'00':(6,7), '10':(5,9), '01':(5,7), '11':(-20,-14)}
    for ax, q in zip(axes.flat, data['contrasts']):
        rows = {r['cell']:r for r in data['rows'] if r['case']==q['case'] and r['arm']==q['arm']}
        origin = np.array([rows['00']['east_km'],rows['00']['north_km']])
        points = {}
        for cell, row in rows.items():
            v = (np.array([row['east_km'],row['north_km']])-origin)*1000
            points[cell] = v
            ax.scatter(*v,s=42,color=colors[cell],zorder=3)
            ax.annotate(cell,v,xytext=offsets[cell],textcoords='offset points',fontsize=10)
        a = np.array(q['vectors_km']['symmetric_noise'])*1000
        b = np.array(q['vectors_km']['symmetric_prior'])*1000
        ax.annotate('',a,xytext=[0,0],arrowprops=dict(arrowstyle='->',color=colors['10'],lw=2.4))
        ax.annotate('',a+b,xytext=a,arrowprops=dict(arrowstyle='->',color=colors['01'],lw=2.4))
        p = np.array(list(points.values()))
        low, high = p.min(axis=0), p.max(axis=0)
        center = (low+high)/2
        half = max(float((high-low).max()),1.)*.72
        ax.set_xlim(center[0]-half,center[0]+half)
        ax.set_ylim(center[1]-half,center[1]+half)
        ax.set_aspect('equal',adjustable='box')
        label = 'c = 0' if q['arm']=='c0' else 'fitted c'
        ax.set_title(f"{q['case']} · {label}\nNoise {np.linalg.norm(a):.1f} m; prior {np.linalg.norm(b):.1f} m")
        ax.set_xlabel('East displacement from original packet (m)')
        ax.set_ylabel('North displacement from original packet (m)')
        ax.grid(alpha=.25)
    fig.suptitle('Original CFO: separate noise and nuisance-prior effects\nBlue arrow: symmetric noise effect; orange: prior effect\n00 old/old · 10 new noise · 01 new prior · 11 both new; equal east/north scales',fontsize=12)
    for extension in ('png','pdf'):
        fig.savefig(OUT/f'precision_block_vectors.{extension}',dpi=160)
    plt.close(fig)
    files=[SOURCE,ROOT/'mechanism/RF_seal.json',Path(__file__),*OUT.iterdir()]
    receipt={'source_and_figure_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
             'new_fits':0,'GPS_used':False,'reporting_seconds':time.monotonic()-start}
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'files':len(files),'reporting_seconds':receipt['reporting_seconds']}))


if __name__ == '__main__':
    main()
