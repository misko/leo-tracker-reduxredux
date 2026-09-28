"""Static local-grid scientific diagnostic."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
d=json.loads((HERE/'diagnosis.json').read_text());old=json.loads((HERE/'results.json').read_text())
g=d['grid'];a=old['sites']['sacramento'];b=old['sites']['reference']
x=(b['longitude_deg']-a['longitude_deg'])*111.195*np.cos(np.deg2rad(a['latitude_deg']))
y=(b['latitude_deg']-a['latitude_deg'])*111.195
fig,axes=plt.subplots(1,2,figsize=(11,5.3),layout='constrained')
for ax,key,title in zip(axes,('training_log_evidence','predictive_nll'),('Training evidence loss (lower is better)','Held-out predictive NLL (lower is better)')):
    z=np.array([v[key] for v in g]).reshape(5,5).T
    if key=='training_log_evidence':z=z.max()-z
    im=ax.imshow(z,origin='lower',extent=(-12.5,12.5,-12.5,12.5),cmap='viridis_r',aspect='equal')
    plt.colorbar(im,ax=ax,shrink=.8)
    ax.scatter(0,0,s=90,c='white',edgecolors='black',marker='o',label='Original Sacramento estimate')
    ax.scatter(x,y,s=150,c='#ffdd33',edgecolors='black',marker='*',label='Reference position')
    sel=d['training_selected'];ax.scatter(sel['east_km'],sel['north_km'],s=100,c='#ff5555',edgecolors='black',marker='X',label='Training-selected point')
    ax.set(title=title,xlabel='East of Sacramento estimate (km)',ylabel='North (km)',xticks=[-10,-5,0,5,10],yticks=[-10,-5,0,5,10])
axes[0].legend(loc='upper left',fontsize=8)
fig.suptitle('58 tracks: a better model score can move the location farther from truth',fontsize=13)
fig.supxlabel('Conditional Sacramento shortlist • 5 km grid • truth excluded from position selection',fontsize=10)
fig.savefig(HERE/'local_grid.png',dpi=180)
