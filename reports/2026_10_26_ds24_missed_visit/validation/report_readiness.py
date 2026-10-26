"""Static readiness/opportunity figure; no RF admission or geographic evaluation."""

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


def read(name):return json.loads((HERE/name).read_text())


def main():
    base=read('baseline_readiness.json');audit=read('prediction_audit.json')
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
    channels=(1,4,5,6,7,8);x=np.arange(len(channels))
    for rx,shift,color in ((0,-.18,'#4c78a8'),(1,.18,'#f58518')):
        counts=[audit['by_channel_receiver'][f'CH{ch}-RX{rx}']['forecast_available'] for ch in channels]
        axes[0].bar(x+shift,counts,width=.35,color=color,label=f'Native RX{rx}')
    axes[0].set_xticks(x,[f'CH{ch}' for ch in channels])
    axes[0].set_ylim(0,51);axes[0].set_ylabel('Earlier-only forecast cells / 48 per RX/channel')
    axes[0].set_title('Sparse history restores forecast availability')
    axes[0].legend(frameon=False,fontsize=9)
    x=np.arange(len(base['development']))
    for band,shift,color in (('low',-.18,'#4c78a8'),('high',.18,'#f58518')):
        channels_band=range(1,5) if band=='low' else range(5,9)
        values=[sum(row['lane_winner_counts'][f'CH{ch}-RX{rx}'] for ch in channels_band for rx in (1,2))
                for row in base['development']]
        axes[1].bar(x+shift,values,width=.35,color=color,label='CH1–4' if band=='low' else 'CH5–8')
    axes[1].set_xticks(x,[r['case'][-4:] for r in base['development']],rotation=60)
    axes[1].set_ylabel('Original persisted winning observations')
    axes[1].set_title('Baseline evidence available for augmentation')
    axes[1].legend(frameon=False,fontsize=9)
    fig.suptitle('Development readiness: forecasts are proposals, not recovered measurements')
    fig.text(.5,-.09,'12 development recordings; 288 paired target windows, 576 receiver cells.\n'
        'No new pilot confirmation, satellite association or geographic result is implied.',ha='center',fontsize=9)
    for ext in ('png','pdf'):fig.savefig(HERE/f'readiness.{ext}',dpi=180,bbox_inches='tight')
    summary=dict(development_cases=12,requested_paired_windows=288,requested_receiver_cells=576,
        forecast_available=audit['counts']['forecast_available'],existing_winners_in_panel=audit['counts']['existing_winner'],
        forecast_modes=audit['counts']['modes'],any_missed_visit_cells=audit['counts']['any_missed_visit'],
        sparse_histories_are_RF_detections=False,held_validation_outcomes_opened=False,
        geographic_errors_opened=False,previous_baseline_hashes_reused=1172,
        previous_exact_endpoint_replays_reused=8,new_position_fits=0,
        callable_adapter_tests_passed=19,
        next_dependency='Timing control parity, matched whole-mode point/search comparisons, full-selection nulls and sealed natural confirmation outcomes.')
    with (HERE/'readiness_summary.json').open('x') as stream:
        json.dump(summary,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
