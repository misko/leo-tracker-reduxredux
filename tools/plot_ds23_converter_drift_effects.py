"""Separate RF-score gains from location changes; report-only visualization."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_converter_drift import OUT
from run_algo01_ds23_sample import read


def main():
    if not read(OUT/'cohort_verification.json')['qualified']:raise ValueError('RF replay required')
    with (OUT/'position_comparison.csv').open() as handle:
        rows=[r for r in csv.DictReader(handle) if r['arm']=='fitted_c']
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,law in zip(axes,('LNB','tuner')):
        for kind,color,label in (('starlink_adaptive_hop_iq','#4679ab','Adaptive: one LNB reference'),
                                  ('short_window_iq_recording','#c27b3d','Fast: recorded dual references')):
            subset=[r for r in rows if r['method']==law and r['format']==kind and r['accepted']=='True']
            ax.scatter([float(r['RF_bound_gain']) for r in subset],
                [float(r['policy_error_km'])-float(r['incumbent_error_km']) for r in subset],
                color=color,label=label,alpha=.8)
        failed=[r for r in rows if r['method']==law and r['accepted']!='True']
        if failed:ax.scatter([0],[0],color='gray',marker='x',s=70,label=str(len(failed))+' failed gates: exact fallback')
        ax.axhline(0,color='black',lw=.8);ax.axvline(0,color='black',lw=.8);ax.grid(alpha=.15)
        ax.set(title=law+'-scaled smooth receiver drift',xlabel='Full RF bound gain (positive = better fit)',
            ylabel='Position-error change (km; negative = better location)');ax.legend(fontsize=7)
    fig.suptitle('DS23 · matched c0/fitted-c controls; fitted-c effects shown\n'
        'Same observations and nuisance count; reference metadata remains conditional, especially for fast captures')
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(OUT/'RF_gain_vs_position_change.png',dpi=175);plt.close(fig)


if __name__=='__main__':main()
