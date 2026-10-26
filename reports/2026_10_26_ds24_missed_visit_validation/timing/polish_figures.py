"""Reporting labels only, using sealed summary/CSV; no new scientific scores."""
import csv
import gzip
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def save(fig,name):
    for suffix in ['png','pdf']:fig.savefig(HERE/(name+'.'+suffix),dpi=170,bbox_inches='tight')
    plt.close(fig)


def main():
    summary=read(HERE/'recorded_summary.json');signal=read(HERE/'outcomes/signal.json.gz')['rows']
    with (HERE/'recorded_cells.csv').open() as f:rows=list(csv.DictReader(f))
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(12,4));channels=[1,4,5,6,7,8]
    methods=[('linear','Consistent linear','#777777'),('quadratic_or_fallback','Quadratic / fallback','#246b99'),('legacy_adapter_linear','Legacy adapter linear','#a37b42')]
    for j,(m,label,color) in enumerate(methods):
        axes[0].bar(np.arange(6)+(j-1)*.23,[summary['by_channel'][str(ch)]['methods'][m]['admitted'] for ch in channels],width=.22,color=color,label=label)
    axes[0].set_xticks(range(6),[f'CH {ch}' for ch in channels]);axes[0].set(ylabel='Full 20 ms admissions / 96',title='Same primary branch; no target search');axes[0].legend(fontsize=8)
    for field,label,color in [('quadratic_gain_vs_linear','Quadratic gains over linear','#246b99'),('quadratic_loss_vs_linear','Quadratic losses versus linear','#a34e45')]:
        axes[1].plot(channels,[summary['by_channel'][str(ch)][field] for ch in channels],'o-',label=label,color=color)
    axes[1].set(xlabel='Channel',ylabel='Paired admission transitions',title='Consistent linear versus quadratic / fallback');axes[1].legend(fontsize=8)
    fig.tight_layout();save(fig,'fullwindow_primary_timing')
    fig,axes=plt.subplots(1,3,figsize=(13,3.8))
    for db,color in [(-12,'#246b99'),(-24,'#a37b42')]:
        selected=[r for r in signal if r['db']==db and abs(r['timing_error_samples'])==.5]
        axes[0].scatter([r['donor_CFO_error_hz'] for r in selected],[r['evaluation']['quadratic_or_fallback']['cfo_error_hz'] for r in selected],s=20,alpha=.55,label=f'{db} dB',color=color)
    for y in [-500,500]:axes[0].axhline(y,color='k',ls='--',lw=.8)
    axes[0].set(xlabel='Earlier CFO prediction error (Hz)',ylabel='Later-bin CFO error (Hz)',title='Frequency information beyond accurate carry');axes[0].legend(fontsize=8)
    strong=[r['evaluation']['quadratic_or_fallback']['cfo_error_hz'] for r in signal if r['db']==-12 and abs(r['timing_error_samples'])==.5]
    axes[1].hist(strong,bins=np.arange(-300,301,25),color='#246b99')
    for x in [-100,100]:axes[1].axvline(x,color='#a34e45',ls='--')
    axes[1].set(xlabel='Strong primary later CFO error (Hz)',ylabel='Trials',title='0/48 within 100 Hz; grid origin matters')
    x=[float(r['quadratic_or_fallback_innovation_hz'])/(10_000_000/(44*512)) for r in rows if r['quadratic_or_fallback_admitted']=='True']
    radius=max(10,int(np.ceil(max(abs(value) for value in x))))
    axes[2].hist(x,bins=np.arange(-radius-.5,radius+1.5),color='#246b99')
    axes[2].set(xlabel='Natural admission CFO innovation (bins)',ylabel='Native owners',title='Conditional later-data bin; no precision calibration')
    fig.tight_layout();save(fig,'frequency_innovation_and_grid_origin')


if __name__=='__main__':main()
