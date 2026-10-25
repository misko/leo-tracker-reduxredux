"""Display saved D-only predictions with exact original native ownership."""
import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
PREDICTION = HERE.parent.parent / 'ds24-ch5-prediction-r01/prediction/run02'
SOURCE = HERE.parent.parent / 'ds25-20261024/DS24-0013'


def restore_prediction(graph, conditioned_raw, conditioned_prediction):
    return np.asarray(conditioned_prediction) + np.asarray(graph) - np.asarray(conditioned_raw)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_csv(name):
    with (HERE/name).open() as stream:
        return list(csv.DictReader(stream))


def main():
    began=time.monotonic()
    paths=[Path(__file__),HERE/'OVERLAY_PROTOCOL.md',HERE/'test_overlay.py',
           HERE/'archived_peaks.csv',HERE/'graph_points.csv',HERE/'results.json',SOURCE/'tracks.json',
           HERE.parent.parent/'ds24-next-directions-review-r01/identity/owner02.py']
    paths += [PREDICTION/arm/name for arm in ['c0','fitted_c'] for name in ['joint_background.npz','Dposterior_GL64.npz']]
    bindings={str(p):sha(p) for p in paths}
    (HERE/'overlay_protocol.json').write_text(json.dumps(dict(files=bindings,no_new_scores=True,no_new_orbits=True,plot_interpolation_only=True),indent=2)+'\n')
    tracks=json.loads((SOURCE/'tracks.json').read_text());peaks=read_csv('archived_peaks.csv');points=read_csv('graph_points.csv')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(17,8),layout='constrained')
    rows=[];details=[]
    for row,ch in enumerate([3,4]):
        target=next(t for t in tracks if t['receiver']==2 and t['channel']==ch and f'-T{2 if ch==3 else 0:03d}-' in t['key'])
        times=np.asarray(target['times']);graph=np.asarray(target['values'])
        pp=[p for p in peaks if int(p['channel'])==ch]
        tt=[p for p in points if int(p['channel'])==ch]
        ax=axes[row,0]
        for passed,color,marker,label in [('True','#929292','x','Other stored peak, passes gate'),('False','#cccccc','+','Other stored peak, fails gate')]:
            group=[p for p in pp if p['is_public_winner']=='False' and p['passed_original_fractional_gate']==passed]
            ax.scatter([float(p['time_s']) for p in group],[float(p['graph_gauge_CFO_Hz'])/1000 for p in group],s=15,color=color,marker=marker,label=label)
        for name in sorted({p['component'] for p in tt}):
            group=[p for p in tt if p['component']==name]
            ax.plot([float(p['time_s']) for p in group],[float(p['common_graph_gauge_CFO_Hz'])/1000 for p in group],'.-',lw=1,label=name.split('-RX2-')[1].split('-RF')[0])
        ax.set_ylim(graph.min()/1000-10,graph.max()/1000+10)
        ax.set_title(f'CH{ch}: original native ownership');ax.set_ylabel('Native CFO −2 periods (kHz)')
        for col,arm in enumerate(['c0','fitted_c'],start=1):
            with np.load(PREDICTION/arm/'joint_background.npz') as saved:
                ids=saved['native_ids'];raw=saved['raw_hz'];alltimes=saved['times_s']
            with np.load(PREDICTION/arm/'Dposterior_GL64.npz') as saved:
                mean=saved['prediction_mean_Hz'];sd=saved['prediction_SD_Hz']
            ix=slice(57,81) if ch==3 else slice(81,124)
            px=slice(0,24) if ch==3 else slice(24,67)
            assert ids[ix].tolist()==target['observation_ids']
            assert np.array_equal(alltimes[ix],times)
            prediction=restore_prediction(graph,raw[ix],mean[px]);sigma=sd[px]
            residual=graph-prediction
            aa=axes[row,col]
            inside=[p for p in pp if times[0]<=float(p['time_s'])<=times[-1]]
            for passed,color,marker,label in [('True','#929292','x','Other stored peak, passes gate'),('False','#cccccc','+','Other stored peak, fails gate')]:
                group=[p for p in inside if p['is_public_winner']=='False' and p['passed_original_fractional_gate']==passed]
                stamp=np.array([float(p['time_s']) for p in group])
                observed=np.array([float(p['graph_gauge_CFO_Hz']) for p in group])
                aa.scatter(stamp,observed-np.interp(stamp,times,prediction),s=15,color=color,marker=marker,label=label)
            aa.fill_between(times,-2*sigma,2*sigma,color='#5d91b7',alpha=.25,label='Saved D-only moment ±2 SD')
            aa.plot(times,residual,'o-',ms=3,color='#1d6792',label='Complete original target winner')
            aa.axhline(0,color='black',lw=.7);aa.set_ylim(residual.min()-3000,residual.max()+3000)
            aa.set_title(f'CH{ch}: {arm}, fixed graph alias 0');aa.set_ylabel('CFO − saved D-only prediction (Hz)')
            rows.append(dict(channel=ch,arm=arm,points=len(times),source_ids_verified=True,
                radio_offset_restoration='graph CFO minus saved conditional raw',interpolation_only_other_probe_times=True))
            for i in range(len(times)):
                details.append(dict(channel=ch,arm=arm,native_id=ids[ix][i],time_s=float(times[i]),
                    native_graph_CFO_Hz=float(graph[i]),fixed_parent_radio_mean_Hz=float(graph[i]-raw[ix][i]),
                    saved_D_only_prediction_graph_Hz=float(prediction[i]),saved_prediction_SD_Hz=float(sigma[i]),
                    residual_Hz=float(residual[i])))
        for aa in axes[row]:aa.set_xlabel('Scan time (s)');aa.grid(alpha=.2);aa.legend(fontsize=7,loc='best')
    fig.suptitle('Archived native peak alternatives and existing CH5-only prediction\n'
        'No source reassignment; candidate records share probes; alias0 fixed; bands are not calibrated coverage')
    fig.savefig(HERE/'crossing_detail02.png',dpi=150);fig.savefig(HERE/'crossing_detail02.pdf');plt.close(fig)
    with (HERE/'prediction_overlay.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(details[0]),lineterminator='\n');writer.writeheader();writer.writerows(details)
    assert all(sha(p)==h for p,h in bindings.items())
    summary=dict(rows=rows,seconds=time.monotonic()-began,no_new_scores=True,no_new_orbits=True,
        no_point_removal=True,GPS_used=False,view_is_exploratory=True)
    (HERE/'overlay_results.json').write_text(json.dumps(summary,indent=2)+'\n')
    files=[Path(__file__),HERE/'OVERLAY_PROTOCOL.md',HERE/'test_overlay.py',HERE/'overlay_protocol.json',
           HERE/'prediction_overlay.csv',HERE/'crossing_detail02.png',HERE/'crossing_detail02.pdf',HERE/'overlay_results.json']
    (HERE/'overlay_seal.json').write_text(json.dumps(dict(files={p.name:sha(p) for p in files}),indent=2)+'\n')


if __name__=='__main__':main()
