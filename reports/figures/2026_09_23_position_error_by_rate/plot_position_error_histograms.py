"""Empirical all-track selected-position error densities for the frozen pre-rotation cohort."""
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

root=Path(__file__).resolve().parent
evidence=json.loads((root/'position-histogram-evidence.json').read_text())
groups=defaultdict(list)
rows=[]
for rec in evidence['recordings']:
    if rec['status']!='complete' or rec.get('state')!='diagnostic':
        continue
    assert rec['configuration']['search']['levels_km']==[100,50,25,12.5]
    for prior in rec['priors']:
        error=prior['selected']['horizontal_error_m']/1000
        groups[(prior['name'],rec['sample_rate_hz'])].append(error)
        rows.append({'session_id':rec['session_id'],'capture_start_utc_ns':rec['captured'],
                     'sample_rate_msps':rec['sample_rate_hz']/1e6,'prior':prior['name'],
                     'selected_error_km':error,'search_complete':prior['search_complete'],
                     'selected_spacing_km':prior['selected']['spacing_km'],
                     'selection_rmse_hz':prior['selected']['capped_weighted_rmse_hz']})
assert len(rows)==90
with (root/'position-errors.csv').open('w') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader();writer.writerows(rows)

colors={2500000:'#0072B2',10000000:'#D55E00',15000000:'#009E73'}
styles={2500000:'-',10000000:'--',15000000:':'}
fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained')
summary=[]
histogram_data=[]
for i,prior in enumerate(('sacramento','reno')):
    for rate in colors:
        values=np.asarray(groups[(prior,rate)])
        summary.append({'prior':prior,'sample_rate_msps':rate/1e6,'n':len(values),
                        'median_error_km':float(np.median(values)),
                        'mean_error_km':float(np.mean(values)),
                        'p90_error_km':float(np.percentile(values,90)),
                        'max_error_km':float(values.max()),
                        'within_10_km':int(np.sum(values<=10)),
                        'within_50_km':int(np.sum(values<=50)),
                        'over_100_km':int(np.sum(values>100))})
    for j,(width,xmax) in enumerate(((5,80),(25,750))):
        ax=axes[i,j]
        bins=np.arange(0,751,width,dtype=float)
        for rate,color in colors.items():
            values=np.asarray(groups[(prior,rate)])
            counts,_=np.histogram(values,bins=bins)
            assert counts.sum()==len(values)
            density=counts/(len(values)*np.diff(bins))
            assert np.isclose(np.sum(density*np.diff(bins)),1)
            ax.stairs(density,bins,color=color,linestyle=styles[rate],linewidth=2.2,
                      label=f'{rate/1e6:g} MS/s (n={len(values)})')
            histogram_data.append({'prior':prior,'sample_rate_msps':rate/1e6,
                                   'bin_width_km':width,'bin_edges_km':bins.tolist(),
                                   'counts':counts.tolist(),'density_per_km':density.tolist()})
        view='Close-up: 0–80 km' if j==0 else 'Full range: 0–750 km'
        ax.set_title(f'{prior.title()} prior · {view}\n{width} km bins',fontsize=12)
        ax.set(xlim=(0,xmax),ylim=(0,None),xlabel='Horizontal error to true position (km)',
               ylabel='Density (1/km)')
        ax.grid(alpha=.2);ax.set_axisbelow(True)
        ax.legend(fontsize=9,loc='upper right')
        if j==0:
            omitted=', '.join(f'{rate/1e6:g} MS/s: {sum(v>80 for v in groups[(prior,rate)])}' for rate in colors)
            ax.text(.98,.66,'Results beyond 80 km\n'+omitted,transform=ax.transAxes,
                    ha='right',va='top',fontsize=8,color='#444444')
        else:
            for rate in colors:
                tail=[v for v in groups[(prior,rate)] if v>100]
                if tail:
                    ax.plot(tail,np.zeros(len(tail)), '|',color=colors[rate],markersize=12,clip_on=False)
fig.suptitle('All-track location search: error distributions by capture rate\n'
             'Pre-rotation · 23 Sep 2026, 06:39:14–14:39:14 UTC',fontsize=16)
fig.supxlabel('45 of 48 recordings have results; each curve integrates to 1 over the full range. '
              'Close-ups retain full-sample normalization.\n'
              'One selected location per recording and prior; 100 → 50 → 25 → 12.5 km search, 400-point budget. '
              'Empirical densities, not position-confidence distributions.',fontsize=9)
fig.savefig(root/'position-error-density.png',dpi=180)
fig.savefig(root/'position-error-density.pdf')
(root/'position-error-statistics.json').write_text(json.dumps(summary,indent=2)+'\n')
(root/'position-error-histogram-bins.json').write_text(json.dumps(histogram_data,indent=2)+'\n')
print(json.dumps(summary,indent=2))
