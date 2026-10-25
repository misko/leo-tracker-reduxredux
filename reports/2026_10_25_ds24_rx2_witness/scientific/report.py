"""Report sealed RX2 scores/array diagnostics only; no new propagation or fits."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ARMS = ('c0','fitted_c')
PERIOD = 1/4.4e-6  # frozen retained_track_likelihood.PERIOD


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name,value):
    path=HERE/name
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)
        stream.write('\n')


def main():
    seal=read(HERE/'RF_seal.json')
    for path,expected in seal['files'].items():
        if sha(path)!=expected:raise ValueError('RF seal binding changed: '+path)
    protocol=read(HERE/'protocol02.json')
    execution=read(HERE/'execution.json')
    rows=[];summary=[];residuals=[]
    fig,axes=plt.subplots(3,2,figsize=(13,10),squeeze=False)
    curves,curveaxes=plt.subplots(3,2,figsize=(13,10),squeeze=False)
    colors=plt.get_cmap('tab10')
    for index,source in enumerate(protocol['sources']):
        name='owner'+str(index);directory=HERE/name
        meta=read(directory/'metadata.json') if (directory/'metadata.json').exists() else source
        title=source['component'].split('DS24-0013-')[1].split('-RF')[0]
        primary=read(directory/'c0_screen.json') if (directory/'c0_screen.json').exists() else None
        cat=np.load(directory/'catalogue.npz') if (directory/'catalogue.npz').exists() else None
        observations=np.load(directory/'observations.npz') if (directory/'observations.npz').exists() else None
        for col,arm in enumerate(ARMS):
            ax=axes[index,col];cx=curveaxes[index,col]
            path=directory/(arm+'_result.json')
            screenpath=directory/(arm+'_screen.json')
            screen=read(screenpath) if screenpath.exists() else None
            result=read(path) if path.exists() else None
            failure=read(directory/(arm+'_failure.json')) if (directory/(arm+'_failure.json')).exists() else None
            rank=(screen['ranked_visible_norads'].index(60108)+1 if screen and 60108 in screen['ranked_visible_norads'] else None)
            row=dict(owner=name,component=source['component'],points=len(source['observation_ids']),arm=arm,
                status='complete' if result else 'failed_or_unavailable',
                ordinary_top8=screen['candidate_norads'] if screen else [],ordinary_60108_rank=rank,
                matched_exact_top8=meta.get('exact_candidate_norads',[]),
                raw_physical_winner=result['raw_physical_winner_norad'] if result else None,
                physical_minus_null=result['physical_minus_null'] if result else None,
                precise_order=result['ordering_absolute_precision_qualified'] if result else False,
                order_certificate=result['evidence_order_certificate'] if result else dict(proved=False,reason='result unavailable'),
                original_parent_residual_gates_passed=result['cavity_original_residual_gates_passed'] if result else None,
                failure=failure['error'] if failure else None)
            summary.append(row)
            candidates={q['norad']:q for q in result['candidates']} if result else {}
            norads=meta.get('exact_candidate_norads',primary['candidate_norads'] if primary else [None]*8)
            for rank0,norad in enumerate(norads):
                checkpoint=directory/(arm+'_'+str(norad)+'_checkpoint.json')
                candidate=candidates.get(norad,read(checkpoint) if checkpoint.exists() else {})
                rows.append(dict(owner=name,component=source['component'],points=len(source['observation_ids']),arm=arm,
                    matched_c0_screen_rank=rank0+1,norad=norad,status=candidate.get('status','not_reached'),
                    objective=candidate.get('objective'),absolute_precision_qualified=candidate.get('numerically_qualified',False),
                    support_certified=candidate.get('certified_visibility',False),visible_prior_mass=candidate.get('inner_visible_prior_mass'),
                    lower_log_evidence=candidate.get('full_support_lower_log_integral'),
                    upper_log_evidence=candidate.get('full_support_upper_log_integral')))
            if result:
                objectives=[candidates[n].get('objective') for n in norads]+[result['null']['objective']]
                finite=[x for x in objectives if x is not None and np.isfinite(x)]
                offset=min(finite) if finite else 0.
                plotted=[x-offset if x is not None else np.nan for x in objectives]
                ax.bar(np.arange(len(plotted)),plotted,color=['#477eaa']*8+['#b45a43'])
                ax.set_yscale('symlog',linthresh=1.)
                ax.set_xticks(np.arange(len(plotted)),[str(n) for n in norads]+['null'],rotation=60,ha='right',fontsize=8)
                proof=result['evidence_order_certificate']
                label=(str(proof.get('winner_norad')) if proof.get('winner_kind')=='physical' else 'null') if proof['proved'] else 'unproved'
                ax.text(.02,.97,'finite-pool order: '+label+'\nabsolute precision: '+str(row['precise_order']),transform=ax.transAxes,va='top',fontsize=9)
            else:
                ax.text(.5,.5,'Exact result unavailable\n'+str(row['failure']),ha='center',va='center',transform=ax.transAxes,wrap=True)
            ax.set_title(title+' / '+arm)
            ax.set_ylabel('−2 log evidence − minimum\n(raw point estimates; symlog)')
            ax.grid(axis='y',alpha=.2)
            if observations is not None and cat is not None and screen is not None:
                background=np.load(directory/(arm+'_nomination_background.npz'))
                times=observations['times_s'];raw=background['raw_hz']
                # Every curve uses its OWN ordinary alias. No target fitting.
                for rank0,norad in enumerate(screen['candidate_norads']):
                    j=screen['catalogue_norads'].index(norad)
                    alias=int(np.asarray(screen['coarse_aliases'])[j,0])
                    residual=raw+alias*PERIOD-cat['frequency_hz'][j]
                    rms=float(np.sqrt(np.mean(residual**2)))
                    scatter=float(np.sqrt(np.mean((residual-residual.mean())**2)))
                    residuals.append(dict(owner=name,arm=arm,norad=norad,ordinary_rank=rank0+1,
                        coarse_alias=alias,causal_phase_RMS_Hz=rms,causal_phase_centered_RMS_Hz=scatter,
                        mean_residual_Hz=float(residual.mean()),maximum_absolute_residual_Hz=float(np.max(abs(residual)))))
                    cx.plot(times,residual,marker='.',lw=1.,alpha=.85 if rank0<2 else .35,
                        color=colors(rank0),label=str(norad)+' RMS '+format(rms,'.0f')+'Hz')
                cx.axhline(0,color='black',lw=.5)
                cx.legend(fontsize=6,ncol=2,loc='best')
            cx.set_title(title+' / '+arm+' nomination background')
            cx.set_xlabel('scan time (s)');cx.set_ylabel('Causal-phase residual (Hz)\ncoarse alias; target nuisances unfitted')
            cx.grid(alpha=.2)
        if cat is not None:cat.close()
        if observations is not None:observations.close()
    fig.suptitle('Three exposed RX2 owners: relative finite-pool evidence, no identity acceptance',fontsize=13)
    fig.tight_layout(rect=(0,0,1,.97));fig.savefig(HERE/'scores.png',dpi=160);plt.close(fig)
    curves.suptitle('Descriptive causal-phase residuals for all ordinary top-eight candidates',fontsize=13)
    curves.tight_layout(rect=(0,0,1,.97));curves.savefig(HERE/'causal_residuals.png',dpi=160);plt.close(curves)
    for name,table in (('candidate_table.csv',rows),('causal_residuals.csv',residuals)):
        with (HERE/name).open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(table[0]) if table else ['unavailable'])
            writer.writeheader();writer.writerows(table)
    write('summary.json',dict(rows=summary,selected_sources=3,selected_owner_arm_contexts=6,
        selected_candidate_contexts=48,completed_owner_arm_contexts=sum(q['status']=='complete' for q in summary),
        absolute_precision_order_contexts=sum(q['precise_order'] for q in summary),
        finite_pool_order_certificates=sum(q['order_certificate']['proved'] for q in summary),
        total_scientific_seconds=execution['total_scientific_seconds'],
        RF_seal_sha256=sha(HERE/'RF_seal.json'),protocol_sha256=sha(HERE/'protocol02.json'),
        position_fits=0,GPS_used=False,operational_identity_assignment=False,discovery_conditioned_evidence=False))
    files=['report.py','summary.json','candidate_table.csv','causal_residuals.csv','scores.png','causal_residuals.png']
    write('report_seal.json',dict(files={name:sha(HERE/name) for name in files},RF_seal_sha256=sha(HERE/'RF_seal.json')))
    print(json.dumps(read(HERE/'summary.json'),indent=2))


if __name__=='__main__':main()
