"""Show expansion gains and losses on the same 15 observation populations."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
DATA=HERE.parent/'2026_10_16_dsx01_fast_association_losses'


def main():
    with (DATA/'regions.csv').open() as stream:
        regions=list(csv.DictReader(stream))
    with (HERE/'window-comparison.csv').open() as stream:
        rows=[r for r in csv.DictReader(stream) if r['arm']=='fitted-c']
    methods=['original','A180','profile1000','expanded_profile']
    labels=['Original','A (180 calls)','Exact profile\n(1000 calls)','Exact profile\n+ 8 candidates']
    table={(r['region_id'],r['method']):r for r in rows}
    values=np.array([[float(table[r['region_id'],m]['association_pct']) for m in methods] for r in regions])
    fig,ax=plt.subplots(figsize=(11.5,9.2),constrained_layout=True)
    im=ax.imshow(values,cmap='YlGnBu',vmin=0,vmax=100,aspect='auto')
    ax.set_xticks(np.arange(4),labels)
    ax.set_yticks(np.arange(15),[
        f"{r['region_id'][-3:]} {r['source_id']} RX{r['receiver']}/CH{r['channel']} {float(r['start_s']):g}–{float(r['end_s']):g}s"
        for r in regions])
    for i,r in enumerate(regions):
        for j,m in enumerate(methods):
            entry=table[r['region_id'],m]
            ax.text(j,i,f"{entry['associated']}/{entry['observations']} ({values[i,j]:.0f}%)",
                    ha='center',va='center',color='white' if values[i,j]>65 else '#111111',fontsize=10)
    ax.set_title('DSX01: recovery degree in every requested window, fitted-c\nFixed observation denominators; expansion changes candidates, and loses support in window 001',pad=16)
    cbar=fig.colorbar(im,ax=ax,shrink=.8)
    cbar.set_label('Satellite-association coverage (%)')
    fig.savefig(HERE/'iteration-expanded-windows.png',dpi=180)
    plt.close(fig)


if __name__=='__main__':
    main()
