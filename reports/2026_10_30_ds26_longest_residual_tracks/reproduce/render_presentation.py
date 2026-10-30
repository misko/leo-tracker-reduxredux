"""Render saved diagnostics only; do not refit or change associations."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
NOTES = {
    'DS26-0265': 'Strong 66102 candidate; unrelated family 52311 exceeds the training graph phase window',
    'DS26-0223': '63595 supported in all six checks; inclusion fails correlated residuals and control convergence',
    'DS26-0050': '63468 supported in all six checks; inclusion fails correlated residuals and control convergence',
    'DS26-0251': '67352 supported in all six checks; correlated residuals and optimization at regional boundary',
    'DS26-0094': 'Identity unresolved: random partitions disagree between 66365 and 58722',
}

def segments(t, lift):
    """Break lines at alias changes or gaps, without removing measured points."""
    return np.split(np.arange(len(t)), np.flatnonzero((np.abs(np.diff(lift)) > 1) | (np.diff(t) > 5)) + 1)

def line(ax, t, y, groups, **kwargs):
    for k, ix in enumerate(groups):
        options = dict(kwargs)
        if k: options.pop('label', None)
        ax.plot(t[ix], y[ix], **options)

def run():
    output = ROOT / 'presentation'
    output.mkdir(exist_ok=True)
    for folder in sorted((ROOT/'orbit-diagnostics-v3').glob('[0-9]*-DS26-*')):
        d = json.loads((folder/'result.json').read_text()); row = d['row']
        points = list(csv.DictReader((folder/'points.csv').open()))
        t = np.array([float(p['time_s']) for p in points])
        raw = np.array([float(p['raw_cfo_hz']) for p in points])
        lifted = np.array([float(p['graph_lifted_hz']) for p in points])
        lift = lifted - raw
        groups = segments(t, lift)
        continuous = segments(t, np.zeros(len(t)))
        lane = list(csv.DictReader((folder/'raw_lane_points.csv').open()))
        track = json.loads(Path(row['tracks_path']).read_text())[row['track_index']]
        assert list(track['observation_ids']) == [p['observation_id'] for p in points]
        fig, axes = plt.subplots(3, 1, figsize=(11.5, 8.4), layout='constrained', sharex=True)
        # Public membership determines color. The target is red even if its
        # internal replay had an unreported association.
        for status, color, label in [('associated','.72','Associated'), ('other_unassociated','#e69f00','Other unassociated'), ('target_residual','#cc3344','Target')]:
            qq = [p for p in lane if p['published_role'] == status]
            axes[0].scatter([float(p['time_s']) for p in qq], [float(p['measured_cfo_hz'])/1000 for p in qq], s=22 if status=='target_residual' else 15, color=color, label=label, zorder=3)
        axes[1].scatter(t,lifted/1000,color='#cc3344',s=17,label='Target GLRT, graph alias lifted',zorder=3)
        for k,piece in enumerate(track['pieces']):
            use=(t>=piece['start_s']) & (t<=piece['end_s'])
            poly=np.polynomial.legendre.legval((t-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz'])
            poly[~use]=np.nan
            line(axes[0],t,(poly-lift)/1000,groups,color='black',lw=.9,label='Graph polynomial' if k==0 else None)
            line(axes[1],t,poly/1000,continuous,color='black',lw=.9,label='Graph polynomial' if k==0 else None)
        for arm,color,style in [('c0','#0072b2','--'),('fitted_c','#009e73','-')]:
            fit=d['trials'][arm]['constant'][0]
            residual=np.asarray(fit['residual_hz'])
            line(axes[0],t,(raw-residual)/1000,groups,color=color,ls=style,lw=1.3,label=f"Orbit {fit['norad']} ({arm})")
            line(axes[1],t,(lifted-residual)/1000,continuous,color=color,ls=style,lw=1.3,label=f"Orbit {fit['norad']} ({arm})")
            line(axes[2],t,residual,continuous,color=color,ls=style,lw=1.1,marker='.',ms=3,label=f"Nominal orbit + phase/offset, {arm}: {fit['rms_hz']:.1f} Hz RMS")
        if 'actual_pipeline_trial' in d:
            z=d['actual_pipeline_trial']['arms']['fitted_c']
            assert np.allclose(z['times_s'],t)
            line(axes[2],t,np.asarray(z['residual_hz']),continuous,color='#aa4499',ls=':',lw=1.6,label=f"Actual inclusion trial, fitted c: {z['RMS_hz']:.1f} Hz RMS")
        if row['case']=='DS26-0094':
            competitor=next(f for f in d['trials']['fitted_c']['constant'] if f['norad']==66365)
            line(axes[2],t,np.array(competitor['residual_hz']),continuous,color='#d55e00',ls='--',lw=1.1,label=f"Alternative 66365, fitted c: {competitor['rms_hz']:.1f} Hz RMS")
        changes=int(np.count_nonzero(np.abs(np.diff(lift))>1))
        axes[0].set_title(f'Native GLRT measurements; {changes} alias-branch transitions; lines break at wraps and gaps >5 s',fontsize=9)
        axes[0].set_ylabel('Raw CFO (kHz)')
        axes[1].set_title('Same target after the original graph alias lift — no new fit or point removal',fontsize=9)
        axes[1].set_ylabel('Lifted CFO (kHz)')
        axes[2].set_ylabel('Residual (Hz)');axes[2].set_xlabel('Scan time (s)')
        axes[2].axhline(0,color='.4',lw=.7)
        for ax in axes:
            ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=2,loc='best')
        fig.suptitle(f"#{row['rank']} {row['case']} · RX{row['receiver']} CH{row['channel']} · {row['span_s']:.2f} s · {row['residual_points']} points\n{NOTES[row['case']]}",fontsize=11)
        fig.savefig(output/(row['case']+'.png'),dpi=155)
        fig.savefig(output/(row['case']+'.pdf'))
        plt.close(fig)

if __name__=='__main__':run()
