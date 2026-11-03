"""Expanded-subset orbit overlays with every stored GLRT row represented."""
from pathlib import Path
import csv
import json

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from exhaustive_subset import Case, HERE
from plot_tle_doppler_overlay import calibrated_points, orbital_curve
from finite_set_fit import snapshot_files

OUT = HERE / 'exhaustive-subset'


def alias_background(alias, assigned):
    unused = np.setdiff1d(np.arange(len(alias)), assigned)
    rr = np.repeat(unused, alias.shape[1])
    cc = np.tile(np.arange(alias.shape[1]), len(unused))
    _, keep = np.unique(np.column_stack([rr, alias[rr,cc]]), axis=0, return_index=True)
    return rr[keep], cc[keep]


def main():
    receipt = dict(scope=__doc__, scans=[], source_hashes=snapshot_files([__file__]))
    for label in 'AB':
        case = Case(label)
        path = OUT/f'{label}-receipt.json'
        saved = json.loads(path.read_text())
        fit = saved['arms']['fitted-c']['fit']
        params = np.array(fit['parameters'])
        coeff = np.array(fit['rf_coefficient_hz_per_ghz'])
        numbers = np.array(saved['catalog_numbers'])
        indices = [int(np.flatnonzero(case.data.numbers==n)[0]) for n in numbers]
        raw, _ = case.predict(indices, params, coeff)
        d = case.data
        rx = np.array(d.receiver, int)
        nuisance = params[2+2*rx]+params[3+2*rx]*(d.times-d.reference_time_s)+case.features@coeff
        points = calibrated_points(d.measured, raw, d.rf, nuisance, case.prepared.alias_hz)
        dense_t = np.arange(0,300.001,.25)
        curves, visible = orbital_curve(d, params, indices, dense_t)
        assignment_path = OUT/f'{label}-fitted-c-assignments.csv'
        records = list(csv.DictReader(assignment_path.open()))
        rows = np.array([int(r['row_index']) for r in records])
        cols = np.array([int(np.flatnonzero(numbers==int(r['catalog_number']))[0]) for r in records])
        np.testing.assert_allclose(points['residual_hz'][rows,cols], [float(r['residual_hz']) for r in records], atol=1e-6)
        assert len(np.unique(rows))==len(rows)
        rr, cc = alias_background(points['alias_integer'], rows)
        assert set(rr).isdisjoint(rows)
        assert set(rr)|set(rows)==set(range(len(d.times)))
        colors = plt.get_cmap('tab20')(np.arange(len(numbers)))
        fig, axes = plt.subplots(2,1,figsize=(17,12),sharex=True,sharey=True)
        for receiver, ax in enumerate(axes):
            bg = rx[rr]==receiver
            ax.scatter(d.times[rr[bg]], points['doppler_hz'][rr[bg],cc[bg]]/1000,
                       c='.48',s=4,alpha=.30,linewidths=0,rasterized=True,zorder=0)
            for col, number in enumerate(numbers):
                ax.plot(dense_t,np.where(visible[:,col],curves[:,col]/1000,np.nan),
                        color=colors[col],lw=1.1,alpha=.75,zorder=1)
                used = rows[(cols==col)&(rx[rows]==receiver)]
                ax.scatter(d.times[used],points['doppler_hz'][used,col]/1000,
                           c=[colors[col]],s=10,linewidths=0,zorder=2)
            count = int(np.sum(rx[rows]==receiver))
            ax.set_title(f'RX{receiver} · {count:,} assigned / {int(np.sum(rx==receiver))-count:,} unassigned stored peaks')
            ax.set_ylabel('Calibrated Doppler (kHz)')
            ax.set_xlim(0,300)
            ax.grid(alpha=.18)
        axes[-1].set_xlabel('Receive time since capture start (s)')
        old = set(saved['baseline']['catalog_numbers'])
        handles = [Line2D([],[],color=colors[i],lw=2,label=f'{n}'+(' *' if n not in old else '')) for i,n in enumerate(numbers)]
        handles.append(Line2D([],[],color='.48',marker='.',ls='',label='Unassigned alias alternatives'))
        fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.047),ncol=7,fontsize=10)
        fig.suptitle(f'DS13 scan {label} · expanded subset: {len(numbers)} satellites\n'
                     'Orbit curves + assigned GLRT peaks + all unassigned peaks',fontsize=17)
        fig.text(.5,.014,'* Newly admitted satellite. Colors identify satellites; gray = unassigned, shown once per distinct candidate-nearest alias branch.\n'
                 'All stored rows included, including exact-alias copies. RX/RF calibration removed; normalized to 11.085 GHz. No extra detrending.\n'
                 'Timing-adjusted fitted-c trajectories at the known roof position. In-sample associations, not confirmed identities.',ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.15,1,.94))
        target = OUT/f'{label}-orbits-all-glrt.png'
        fig.savefig(target,dpi=160)
        plt.close(fig)
        receipt['source_hashes'].update(snapshot_files([path,assignment_path]))
        receipt['scans'].append(dict(scan=label,total_rows=len(d.times),assigned_rows=len(rows),
                                     unassigned_rows=len(d.times)-len(rows),gray_alias_markers=len(rr),
                                     output=str(target),catalog_numbers=numbers.tolist()))
        print(receipt['scans'][-1],flush=True)
    (OUT/'orbit-plot-receipt.json').write_text(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
