import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

root=Path('/tmp/three-track-investigation/space-track-pipeline-rerun')
data=json.loads((root/'three_track_exception_audit.json').read_text())
fig,axes=plt.subplots(1,3,figsize=(15,4.6),layout='constrained')
for ax,name,label in zip(axes,['early_ch2','ch4','late_ch2'],['RX1 CH2 · 50–75 s · candidate 69433','RX1 CH4 · 40–100 s · candidate 69333','RX1 CH2 · 170–190 s · candidate 69522']):
    rows=sorted((r for r in data['points'] if r['track']==name),key=lambda r:r['time_s'])
    t=np.array([r['time_s'] for r in rows]); residual=np.array([r['intended_residual_hz'] for r in rows])
    threshold=np.array([r['clutter_crossover_absolute_residual_hz'] for r in rows])
    ax.fill_between(t,-threshold,threshold,color='#dddddd',alpha=.5,label='Candidate beats clutter')
    ax.axhline(0,color='black',lw=.6)
    ax.plot(t,residual,'o-',ms=3,lw=.6,color='#187f9b',label='Residual to candidate')
    for row in rows:
        if not row['exception']: continue
        ax.scatter(row['time_s'],row['intended_residual_hz'],s=65,facecolors='none',edgecolors='#cc3b32',lw=2,zorder=5)
        annotation='Crossing: competing satellite wins' if name=='ch4' else '403 Hz; clutter cutoff 377 Hz'
        ax.annotate(annotation,(row['time_s'],row['intended_residual_hz']),xytext=(.04,.93),textcoords='axes fraction',fontsize=8,arrowprops=dict(arrowstyle='->',color='#cc3b32'),color='#b32b23')
    ax.set(title=label,xlabel='Time from scan origin (s)',ylim=(-460,490))
    ax.grid(alpha=.2)
axes[0].set_ylabel('Frequency residual (Hz)')
axes[0].legend(loc='lower left',fontsize=8)
fig.suptitle('Remaining exceptions in the saved experimental fit\nFixed calibration and correction; no refit or forced associations',fontsize=13)
fig.savefig(root/'three_track_exceptions.png',dpi=180)
print(root/'three_track_exceptions.png')
