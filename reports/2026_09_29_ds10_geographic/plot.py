"""Render the complete predeclared DS10 reference-distance comparison."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


if __name__=='__main__':
    data=json.loads((HERE/'summary.json').read_text())
    assert data['complete'] and len(data['rows'])==12
    panels=['N8_0','N8_1','N8_2','N24']
    fig,ax=plt.subplots(figsize=(9,5),layout='constrained')
    x=np.arange(4);width=.24
    for j,(height,color) in enumerate([(0,'#245b87'),(20,'#549fc6'),(40,'#91c9d5')]):
        values=[next(r['reference_distance_m']/1000 for r in data['rows'] if r['panel']==panel and r['height_m']==height) for panel in panels]
        bars=ax.bar(x+(j-1)*width,values,width,label=f'{height} m fixed height',color=color)
        ax.bar_label(bars,labels=[f'{v:.2f}' for v in values],fontsize=8,padding=3)
    ax.axhline(1,color='#a43b35',ls='--',lw=1,label='1 km threshold')
    ax.axhline(data['configured_center_reference_distance_m']/1000,color='#555555',ls=':',lw=1.5,label='Configured center (no RF fit)')
    ax.set_xticks(x,['N8 subset 0','N8 subset 1','N8 subset 2','N24 pooled'])
    ax.set_ylabel('Distance to assumed reference (km)')
    ax.set_title('DS10: frozen baseline and declared height scenarios')
    ax.set_ylim(0,2.45);ax.legend(loc='upper left',fontsize=8,ncol=2)
    ax.spines[['top','right']].set_visible(False)
    ax.set_xlabel('Same installation/reference assumed; heights are scenarios, not surveyed values.',fontsize=8,labelpad=12)
    fig.savefig(HERE/'reference-distance.png',dpi=160)
    plt.close(fig)
