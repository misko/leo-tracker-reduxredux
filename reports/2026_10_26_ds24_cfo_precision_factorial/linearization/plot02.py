"""Layout-only revision from the unchanged saved comparison CSV."""
import time
STARTED=time.monotonic()
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows=list(csv.DictReader((HERE/'comparison.csv').open()))
fig,axes=plt.subplots(2,2,figsize=(11,10))
fig.subplots_adjust(left=.09,right=.98,bottom=.07,top=.80,hspace=.34,wspace=.28)
styles=[('Hdelta','Saved local Hδ','#0072B2','o','-'),('isolated_CFO','CFO at original fixed packet','#D55E00','x','--'),
        ('full_conditional','Full conditional change','#009E73','s','-'),('previous_VI','Previous VI change','#CC79A7','+','--')]
for ax,row in zip(axes.flat,rows):
    for key,label,color,marker,ls in styles:
        east,north=float(row[key+'_east_m']),float(row[key+'_north_m'])
        ax.plot([0,east],[0,north],ls=ls,color=color,lw=1,alpha=.6)
        ax.scatter([east],[north],color=color,marker=marker,s=80,label=label,zorder=3)
    ax.axhline(0,color='.5',lw=.6);ax.axvline(0,color='.5',lw=.6);ax.grid(alpha=.2)
    ax.set(title=row['case']+' '+row['arm'].replace('fitted_c','fitted c'),xlabel='East displacement (m)',ylabel='North displacement (m)')
    ax.set_aspect('equal',adjustable='datalim');ax.margins(.16)
    ax.text(.03,.04,f"H vs fixed-packet CFO: {float(row['H_vs_isolated_difference_norm_m']):.3f} m",transform=ax.transAxes,fontsize=9)
handles,labels=axes.flat[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.92),ncol=2,fontsize=9)
fig.suptitle('Local response agrees with CFO-only movement at fixed precision\nPosthoc exposed-data comparison; no geographic accuracy claim',fontsize=12,y=.985)
fig.savefig(HERE/'isolated_CFO_response02.png',dpi=170);fig.savefig(HERE/'isolated_CFO_response02.pdf');plt.close(fig)
seconds=time.monotonic()-STARTED
first=json.loads((HERE/'summary.json').read_text())['cumulative_numeric_seconds']
assert seconds+first<5
with(HERE/'plot02_seal.json').open('x')as f:json.dump(dict(source_sha256=sha(__file__),comparison_sha256=sha(HERE/'comparison.csv'),
    layout_only=True,cumulative_numeric_seconds=first+seconds,files={p.name:sha(p)for p in (HERE/'isolated_CFO_response02.png',HERE/'isolated_CFO_response02.pdf')}),f,indent=2);f.write('\n')
print('cumulative_saved_only_seconds',first+seconds)
