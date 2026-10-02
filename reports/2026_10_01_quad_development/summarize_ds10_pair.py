"""Plot the full outlier pair and audit RF-scaled coarse aliases."""
import json
from pathlib import Path
import subprocess
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from prepare_block import verify_reader,RUNTIME
HERE=Path(__file__).resolve().parent


def main():
    root=HERE/'ds10-pair-inspection-v1'
    result=sealed(root/'result.json');freeze=sealed(root/'sources.json');verify_sources(freeze['source_sha256']);verify_sources(freeze['inputs'])
    overlay=sealed(HERE/'quality-overlay-v4/overlay.json');q=next(r for r in overlay['results'] if r['unit']=='DS10-F001')
    by_track={t['track_id']:t['points'] for t in q['tracks']}
    before=verify_reader()
    code='import inspect,json; from dataclasses import asdict; import leo.analysis.persistent_hop_trajectory as m; print(json.dumps(dict(config=asdict(m.PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6)),module_source=inspect.getsource(m))))'
    call=subprocess.run(['sudo','-n','-u','leo',RUNTIME,'-c',code],capture_output=True,text=True,check=True,timeout=30)
    public=json.loads(call.stdout);after=verify_reader();config=public['config']
    fig,axes=plt.subplots(3,1,figsize=(10,8),sharex=True);rows=[]
    for row in result['tracks']:
        samples=row['samples'];points=by_track[row['track_id']];t=np.array([s['time_s'] for s in samples]);y=np.array([s['centered_residual_hz'] for s in samples]);keep=np.array([s['retained'] for s in samples]);rx=row['receiver_id']
        rema=np.array([(p['measured_cfo_hz']*config['canonical_rf_hz']/p['actual_rf_hz']-p['normalized_dealiased_cfo_hz'])/(config['alias_spacing_hz']*config['canonical_rf_hz']/p['actual_rf_hz']) for p in points])
        rounded=np.rint(rema);error=float(np.max(abs(rema-rounded)));assert error<1e-8
        axes[0].plot(t,y,'.-',alpha=.7,label=f'RX{rx}: full track');axes[0].scatter(t[keep],y[keep],s=60,facecolors='none',edgecolors=f'C{rx}',label=f'RX{rx}: retained')
        axes[1].plot(t,[s['margin'] for s in samples],'.-',label=f'RX{rx}')
        axes[2].step(t,rounded,where='mid',label=f'RX{rx}')
        rows.append(dict(receiver_id=rx,summary=row['summary'],inferred_relative_alias_indices=rounded.astype(int).tolist(),maximum_integer_error=error,
                         coarse_alias_spacing_normalized_hz=config['alias_spacing_hz']*config['canonical_rf_hz']/points[0]['actual_rf_hz']))
    for ax in axes:ax.legend(loc='best');ax.grid(alpha=.2)
    axes[0].set_ylabel('Residual about retained mean (Hz)');axes[1].set_ylabel('Detector margin');axes[2].set_ylabel('Inferred coarse alias index');axes[2].set_xlabel('Seconds from scan start')
    fig.suptitle('DS10 outlier pair assigned to NORAD 64429: fixed-state diagnostic')
    fig.tight_layout();fig.savefig(HERE/'ds10-pair-inspection-v1.png',dpi=160);plt.close(fig)
    save(HERE/'ds10-pair-summary-v1.json',dict(rows=rows,reader_before=before,reader_after=after,public_projection=public,
        inputs={str(root/'result.json'):digest(root/'result.json'),str(HERE/'quality-overlay-v4/overlay.json'):digest(HERE/'quality-overlay-v4/overlay.json')},
        sources={str(Path(__file__).resolve()):digest(__file__)},qualification='Alias indices algebraically reconstructed under verified pinned RF-scaled coarse alias formula; not a new candidate export or localization result.'))
    print(rows)


if __name__=='__main__':main()
