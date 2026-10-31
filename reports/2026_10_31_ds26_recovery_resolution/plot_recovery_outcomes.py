"""Display association gains separately from reporting-only position error."""
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).parent
rows=list(csv.DictReader((ROOT/'phase-inclusion/qualified-coverage.csv').open()))
fig,axs=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
labels=[]
for i,r in enumerate(rows):
    labels.append(r['case'].replace('DS26-','')+' / '+r['arm'].replace('fitted_c','fitted c').replace('c0','c = 0'))
    color='#2166ac' if r['arm']=='c0' else '#df8700'
    for ax,a,b in [(axs[0],float(r['control_percent_all_GLRT']),float(r['addition_percent_all_GLRT'])),
                   (axs[1],float(r['control_position_error_m'])/1000,float(r['addition_position_error_m'])/1000)]:
        ax.annotate('',xy=(b,i),xytext=(a,i),arrowprops=dict(arrowstyle='->',color=color,lw=2))
        ax.scatter([a],[i],s=50,facecolor='white',edgecolor=color,zorder=3)
        ax.scatter([b],[i],s=30,color=color,zorder=3)
        ax.text((a+b)/2,i-.22,f'{a:.2f} → {b:.2f}',ha='center',fontsize=9)
axs[0].set_xlabel('Associated / all original GLRT (%)');axs[0].set_xlim(71.8,75.3)
axs[0].set_title('Targeted recovery: 26 points in 0044; 30 in 0154')
axs[1].set_xlabel('Position error (km), reporting only');axs[1].set_xlim(.3,4.1)
axs[1].axvline(.5,color='crimson',ls='--',lw=1,label='500 m objective');axs[1].legend(loc='lower right')
axs[1].set_title('One scan improves slightly; the other worsens')
for ax in axs:
    ax.set_yticks(range(len(rows)),labels);ax.set_ylim(3.5,-.6);ax.grid(axis='x',alpha=.2)
fig.suptitle('Research-qualified additions: association coverage and accuracy are different outcomes\nOpen circle = matched control; filled circle = addition. No production change.')
fig.savefig(ROOT/'recovery-outcomes.png',dpi=150);fig.savefig(ROOT/'recovery-outcomes.pdf');plt.close(fig)
