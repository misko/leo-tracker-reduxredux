"""Publish figures and compact receipts for covariance and later-TLE tests."""

import argparse
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


def main(args):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    out=args.output;out.mkdir(parents=True,exist_ok=False)
    records={}
    for directory in ('correlated-noise-v3','covariance-splits-v1','post-tle-v1'):
        for path in sorted((args.study/directory).glob('*.json')):
            records[str(path.relative_to(args.study))]=json.loads(path.read_text())
    def read(name):return records['correlated-noise-v3/'+name+'.json']
    calibration=read('calibration');extras=read('target_entries')
    position={name:read(name+'_positions') for name in ('white','correlated','transferred')}
    validation={name:read(name+'_validation') for name in position}
    (out/'receipts.json.gz').write_bytes(gzip.compress(json.dumps(records,separators=(',',':')).encode(),mtime=0))
    summary=dict(training_points=sum(len(r['times']) for r in calibration['rows']),
        training_families=sorted({r['norad'] for r in calibration['rows']}),
        noise_model=calibration['best_correlated'],white_control=calibration['null'],
        training_penalized_gain=calibration['null']['selection_score']-calibration['best_correlated']['selection_score'],
        production_promoted=False,prototype_coverage_percent=2703/3283*100,results={})
    for name in position:
        summary['results'][name]={}
        for arm,r in position[name].items():
            held=validation[name][arm]['held']
            summary['results'][name][arm]=dict(position_east_north_km=r['endpoint_east_north_km'],
                position_latlon=r['endpoint_latlon'],movement_m=r['displacement_from_CH1_m'],
                held_RMS_hz=held['RMS_hz'],held_score=held['objective'],
                held_joint_pass=held['noise']['noise_screen_pass'],
                held_each_track_pass=all(g['noise_screen_pass'] for g in held['per_track_noise'].values()),
                full_joint_pass=r['target']['noise']['noise_screen_pass'],
                full_each_track_pass=all(g['noise_screen_pass'] for g in r['target']['per_track_noise'].values()),
                original_gates_pass=all(g['compatible'] for g in r['gates']['tracks']+r['linear_gates']),
                proposed_associated_points=r['proposed_associated_points'])
    split=records['covariance-splits-v1/results.json']['results']
    summary['random_splits']=[dict(seed=r['seed'],withheld_blocks=r['checks']['correlated']['c0']['split']['withheld_blocks'],
        arms={a:dict(score_gain=r['checks']['white'][a]['held']['objective']-r['checks']['correlated'][a]['held']['objective'],
                     each_track_pass=all(g['noise_screen_pass'] for g in r['checks']['correlated'][a]['held']['per_track_noise'].values()))
              for a in ('c0','fitted_c')}) for r in split]
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

    fig,axes=plt.subplots(2,2,figsize=(12,8),sharex=True)
    for col,name in enumerate(('white','correlated')):
        r=position[name]['fitted_c'];t=np.asarray(r['target_times_s']);raw=np.asarray(r['target_raw_hz'])
        # Original GLRT per-track times are saved in the initial study receipt.
        inv=json.loads((args.study/'high-channels-v2/inventory.json').read_text())
        lengths=[e['points'] for e in extras]
        stack=np.concatenate([s['active']['times_s'] for s in inv['screens']])
        owner=np.repeat(np.arange(2),lengths)[np.argsort(stack,kind='stable')]
        for k,color in enumerate(('#b91c1c','#2563eb')):
            use=owner==k
            residual=raw[use]-r['physical_target_checks'][k]['bias_hz']
            axes[0,col].plot(t[use],residual,'.-',color=color,label=f'CH{k+7}')
            axes[1,col].plot(t[use],np.asarray(r['target']['whitened'])[use],'.-',color=color,label=f'CH{k+7}')
        axes[0,col].set_title('Independent-noise control' if name=='white' else 'Shared covariance from other families')
        axes[0,col].set_ylabel('Residual after curve constant (Hz)')
        axes[1,col].set_ylabel('Whitened innovation (standard deviations)')
        axes[1,col].set_xlabel('Time in scan (s)')
        axes[1,col].axhspan(-2,2,color='gray',alpha=.12)
    for ax in axes.flat:
        ax.axhline(0,color='gray',lw=.7);ax.grid(alpha=.2);ax.legend(fontsize=9)
    fig.suptitle('All 113 points retained in predictive position fits — fitted c\n'
                 'Shared error is modeled in the covariance; raw residuals need not become white')
    fig.tight_layout();fig.savefig(out/'full_curve_innovations.png',dpi=160);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    labels=['Independent noise','Shared covariance','Transferred correction']
    for k,arm in enumerate(('c0','fitted_c')):
        x=np.arange(3)+(-.18 if k==0 else .18)
        for ax,key in zip(axes,('RMS_hz','objective'),strict=True):
            ax.bar(x,[validation[name][arm]['held'][key] for name in position],width=.36,label=arm)
            ax.set_xticks(np.arange(3),labels,rotation=12);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Withheld raw residual RMS (Hz)')
    axes[1].set_ylabel('Withheld −2 log predictive density (lower is better)')
    for ax in axes:ax.legend()
    fig.suptitle('45 randomly withheld GLRT points, shared CH7/CH8 time blocks\n'
                 'Transfer improves RMS but narrowly fails CH7 held-out slope in fitted c')
    fig.tight_layout();fig.savefig(out/'withheld_prediction.png',dpi=160);plt.close(fig)

    fig,ax=plt.subplots(figsize=(10,4.8))
    for k,arm in enumerate(('c0','fitted_c')):
        gain=[r['arms'][arm]['score_gain'] for r in summary['random_splits']]
        passed=[r['arms'][arm]['each_track_pass'] for r in summary['random_splits']]
        x=np.arange(8)+(-.12 if k==0 else .12)
        ax.scatter(x,gain,marker='o' if k==0 else 's',s=65,c=['#15803d' if p else '#dc2626' for p in passed],label=arm)
    ax.set(xlabel='Fixed random seed',ylabel='Predictive score gain over independent noise',xticks=np.arange(8))
    ax.axhline(0,color='gray');ax.grid(alpha=.2);ax.legend()
    ax.set_title('All splits improve predictive score; per-track gates pass in 6/8\n'
                 'Red: CH7 mean fails for the same withheld blocks, 96–120 s')
    fig.tight_layout();fig.savefig(out/'split_robustness.png',dpi=160);plt.close(fig)

    audit=records['post-tle-v1/archive_audit.json']
    origin=datetime.fromisoformat(audit['observation_utc']).timestamp()
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    for norad,color in ((57701,'#2563eb'),(58101,'#b91c1c')):
        xs=[(datetime.fromisoformat(r['collected_utc']).timestamp()-origin)/3600 for r in audit['timeline']]
        ys=[(r['targets'][str(norad)]['epoch_utc_ns']/1e9-origin)/3600 for r in audit['timeline']]
        axes[0].plot(xs,ys,'o-',color=color,label=str(norad))
    axes[0].set(xlabel='Snapshot collection: hours after observation',ylabel='Element epoch: hours relative to observation',
                title='Later downloads repeat the same candidate orbits')
    for k,(kind,style) in enumerate((('causal','-'),('post_observation','--'))):
        for row,color in zip(records[f'post-tle-v1/fitted_c_{kind}.json'],('#b91c1c','#2563eb'),strict=True):
            ch=row['component'].split('-CH')[1].split('-')[0]
            axes[1].plot(row['times_s'],row['residual_hz'],style,color=color,label=f'CH{ch} {kind}')
    axes[1].set(xlabel='Time in scan (s)',ylabel='Profile residual (Hz)',title='Best candidate remains 57701; curves overlap exactly')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(out/'post_tle_comparison.png',dpi=160);plt.close(fig)

    root=Path(__file__).resolve().parents[1]
    sources=[Path(__file__),*[root/'tools'/s for s in ('correlated_curve_prediction.py',
        'probe_high_channel_correlated_noise.py','probe_high_channels_post_tle.py','validate_high_channel_covariance_splits.py')]]
    hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    inputs={name:hashlib.sha256((args.study/name).read_bytes()).hexdigest() for name in records}
    inputs['high-channels-v2/inventory.json']=hashlib.sha256((args.study/'high-channels-v2/inventory.json').read_bytes()).hexdigest()
    (out/'provenance.json').write_text(json.dumps(dict(publication_source_sha256=hashes,input_sha256=inputs,
        source_note='Publication versions include subsequent reporting/validation additions; source hashes are not execution snapshots.',
        production_unchanged=True,reference_position_used=False),indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
