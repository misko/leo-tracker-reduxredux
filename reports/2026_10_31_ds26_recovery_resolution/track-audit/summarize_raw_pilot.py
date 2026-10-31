"""Post-seal residual comparison only; no re-estimation or point selection."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent


def read(p):return json.loads(Path(p).read_text())


def main():
    measure=read(OUT/'raw-pilot-measurements.json');seal=read(OUT/'raw-pilot-measurement-seal.json')
    assert hashlib.sha256((OUT/'raw-pilot-measurements.json').read_bytes()).hexdigest()==seal['measurement_sha256']
    assert measure['status']=='complete'
    plan=read(OUT/'raw-plan.json');export=read(OUT/'raw-export-receipt.json');byid={r['observation_id']:r for r in plan['points']}
    audit=read(OUT/'audit.json');target=next(c for c in audit['cases'] if c['case']=='DS26-0265')
    # This is the first orbital-residual read in this reporting-only stage.
    rows=[r for r in measure['rows'] if r['kind']=='target'];times=np.array([byid[r['observation_id']]['time_s'] for r in rows])
    delta=np.array([r['subbin_CFO_delta_hz'] for r in rows]);indices=[]
    for t in times:
        index=int(np.argmin(abs(np.array(target['times_s'])-t)));assert abs(target['times_s'][index]-t)<1e-8;indices.append(index)
    summary=dict(status='complete_negative_pilot',seed=plan['seed'],decoded_windows=export['decoded_windows'],retained_scored_windows=18,
        export_seconds=export['seconds'],measurement_seconds=measure['seconds'],measurement_seal=seal,
        exact_replay_maximum_difference={k:max(abs(r['discrete_replay'][k]) for r in measure['rows']) for k in measure['rows'][0]['discrete_replay']},
        groups={},arms={},no_position_or_bias_or_gate_refit=True,
        comparison='Descriptive12-point comparison to saved30s-reference target-inclusion endpoints learned from original CFOs; no independent frequency or location truth. Not a full120-point recovery or residual-gate recalibration.',
        quantization_scope='Archived residual increments allzero, so exact512 replay is consistent with512 oracle but cannot uniquelyidentify captureFFT size; absolute CFO retains continuous acquisition estimate. This pilot tests fixed-epoch frequency-only refinement, not acquisition/timing redesign.')
    controls_path=OUT/'raw-controls-reporting.json'
    if controls_path.exists():summary['control_orbital_comparison']=read(controls_path)
    for kind in ('target','other_family_control'):
        rr=[r for r in measure['rows'] if r['kind']==kind];dd=np.array([r['subbin_CFO_delta_hz'] for r in rr])
        summary['groups'][kind]=dict(points=len(rr),CFO_delta_min_hz=float(dd.min()),CFO_delta_max_hz=float(dd.max()),CFO_delta_RMS_hz=float(np.sqrt(np.mean(dd*dd))),
            exact_score_gain_min=min(r['continuous_exact_score']-r['archived_exact_score'] for r in rr),
            exact_score_gain_max=max(r['continuous_exact_score']-r['archived_exact_score'] for r in rr),
            margin_gain_min=min(r['continuous_margin']-r['archived_margin'] for r in rr),
            margin_gain_max=max(r['continuous_margin']-r['archived_margin'] for r in rr),
            continuous_margin_min=min(r['continuous_margin'] for r in rr))
    fig,axes=plt.subplots(4,1,figsize=(12,12))
    for arm,r in target['arms'].items():
        before=np.array(r['residual_hz'])[indices];after=before+delta
        summary['arms'][arm]=dict(times_s=times.tolist(),before_residual_hz=before.tolist(),after_residual_hz=after.tolist(),
            before_RMS_hz=float(np.sqrt(np.mean(before*before))),after_RMS_hz=float(np.sqrt(np.mean(after*after))),
            before_mean_hz=float(before.mean()),after_mean_hz=float(after.mean()))
        axes[1].plot(times,before,'o',label=f'{arm} original');axes[1].plot(times,after,'x',label=f'{arm} continuous')
    for kind,marker in [('target','o'),('other_family_control','s')]:
        rr=[r for r in measure['rows'] if r['kind']==kind]
        axes[0].plot([byid[r['observation_id']]['time_s'] for r in rr],[r['subbin_CFO_delta_hz'] for r in rr],marker,label=kind)
    if 'control_orbital_comparison' in summary:
        for arm,r in summary['control_orbital_comparison']['arms'].items():
            axes[2].plot(np.arange(6),[z['original_residual_hz'] for z in r['rows']],'o',label=f'{arm} original')
            axes[2].plot(np.arange(6),[z['continuous_residual_hz'] for z in r['rows']],'x',label=f'{arm} continuous')
        axes[2].set_xlabel('Frozen6controlpoint index (original incumbent geometry)')
    xx=np.arange(18);axes[3].plot(xx,[r['continuous_exact_score']-r['archived_exact_score'] for r in measure['rows']],'o',label='Exact score gain')
    axes[3].plot(xx,[r['continuous_control_score']-r['archived_control_score'] for r in measure['rows']],'s',label='Control score gain')
    axes[3].axvline(11.5,color='gray',linestyle='--');axes[3].set_xlabel('Frozen panel index (12 target, then 6 same-RX/CH controls)')
    axes[0].set_xlabel('Scan time (s)');axes[1].set_xlabel('Scan time (s)')
    for ax,label in zip(axes,['Continuous minus archived CFO (Hz)','Frozen-endpoint target residual (Hz)','Incumbent control residual (Hz)','Score difference'],strict=True):
        ax.axhline(0,color='gray',linewidth=.5);ax.set_ylabel(label);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Frozen18-window DS26-0265 pilot: exact512 replay; same epoch, symbols, conditioning CFO and alias\nMeasurement sealed before orbital comparison; frequency-only refinement worsens the selected target residual RMS',fontsize=11)
    fig.tight_layout();fig.savefig(OUT/'raw-pilot-comparison.png',dpi=160);fig.savefig(OUT/'raw-pilot-comparison.pdf');plt.close(fig)
    (OUT/'raw-pilot-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['exact_replay_maximum_difference','groups','arms']},indent=2))


if __name__=='__main__':main()
