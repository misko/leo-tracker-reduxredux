"""Saved-artifact plots: no new propagation, scores, optimizer or alias choice."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
RUN=HERE/'run02'
ARMS=('c0','fitted_c')
PERIOD=1/4.4e-6


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(name,value):
    with (HERE/name).open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def main():
    seal=read(RUN/'RF_seal.json')
    for path,h in seal['files'].items():
        if sha(path)!=h:raise ValueError('RF binding changed: '+path)
    rows=[];posterior_summary={}
    diagnostic,diagaxes=plt.subplots(1,3,figsize=(15,4.3))
    predictions,predaxes=plt.subplots(2,2,figsize=(13,8),squeeze=False)
    evidence,evaxes=plt.subplots(1,2,figsize=(12,4.5),squeeze=False)
    for col,arm in enumerate(ARMS):
        directory=RUN/arm
        dpath=directory/'D_evidence.json';discovery=read(dpath) if dpath.exists() else None
        posterior_path=directory/'Dposterior.json'
        posterior=read(posterior_path) if posterior_path.exists() else None
        posterior_summary[arm]=posterior
        if posterior:
            value=posterior['GL64']
            with np.load(directory/'Dposterior_GL64.npz') as arrays:
                nodes=arrays['quadrature_nodes'];mass=arrays['quadrature_posterior_mass']
                diagaxes[0].hist(nodes,bins=100,weights=mass,density=True,histtype='step',label=arm)
                prediction_mean=arrays['prediction_mean_Hz'].copy();prediction_sd=arrays['prediction_SD_Hz'].copy()
            diagaxes[1].bar(np.arange(-4,5)+(col-.5)*.35,value['alias_probabilities'],width=.35,label=arm)
            mean=np.r_[value['shape_mean'],value['Dconstant_mean_Hz']/300]
            sd=np.r_[np.sqrt(np.diag(value['shape_covariance'])),value['Dconstant_SD_Hz']/300]
            diagaxes[2].errorbar(np.arange(4)+(col-.5)*.12,mean,yerr=sd,fmt='o',capsize=3,label=arm)
        for row,label in enumerate(('CH3','CH4')):
            result_path=directory/(label+'_result.json')
            result=read(result_path) if result_path.exists() else None
            failure_path=directory/(label+'_failure.json')
            failure=read(failure_path) if failure_path.exists() else None
            same_path=directory/(label+'_same_evidence.json')
            mixed_path=directory/(label+'_mixed_evidence.json')
            primary_path=directory/(label+'_same_primary_checkpoint.json')
            same=read(same_path) if same_path.exists() else None
            mixed=read(mixed_path) if mixed_path.exists() else None
            primary=read(primary_path) if primary_path.exists() else None
            record=dict(arm=arm,witness=label,points=24 if label=='CH3' else 43,
                status='complete' if result else 'failed_or_unavailable',
                winner=result['comparison'].get('winner') if result else None,
                order_proved=result['comparison']['proved'] if result else False,
                joint_same_objective=same.get('objective') if same else None,
                same_nonterminal_primary_objective=primary.get('objective') if primary and not same else None,
                same_final_reference_completed=same is not None,
                mixed_final_reference_completed=mixed is not None,
                joint_mixed_objective=mixed.get('objective') if mixed else None,
                discovery_objective=discovery.get('objective') if discovery else None,
                raw_same_minus_mixed_objective=result['comparison'].get('raw_conditional_same_minus_mixed_objective') if result else None,
                log_odds_lower=result['comparison'].get('joint_log_evidence_odds_bounds',[None,None])[0] if result else None,
                log_odds_upper=result['comparison'].get('joint_log_evidence_odds_bounds',[None,None])[1] if result else None,
                same_absolute_precision=same['numerically_qualified'] if same else False,
                mixed_absolute_precision=mixed['numerically_qualified'] if mixed else False,
                failure=failure.get('error') if failure else None)
            rows.append(record)
            ax=predaxes[row,col]
            if posterior:
                with np.load(directory/'joint_background.npz') as saved:
                    ix=slice(57,81) if label=='CH3' else slice(81,124)
                    px=slice(0,24) if label=='CH3' else slice(24,67)
                    times=saved['times_s'][ix];observed=saved['raw_hz'][ix]
                mu=prediction_mean[px];sd=prediction_sd[px]
                ax.fill_between(times,-2,2,color='#999999',alpha=.25,label='D-only moment ±2 SD')
                for alias in range(-4,5):
                    standardized=(observed+alias*PERIOD-mu)/sd
                    ax.plot(times,standardized,marker='.',ms=2,lw=1,label='alias '+str(alias))
                ax.axhline(0,color='black',lw=.5)
                ax.set_yscale('symlog',linthresh=3.)
                ax.legend(fontsize=6,ncol=2,loc='best')
                ax.set_title(label+' / '+arm+'; stability '+str(posterior['quadrature_stability_passed']))
            else:ax.text(.5,.5,'D-only prediction unavailable',ha='center',transform=ax.transAxes)
            ax.set_xlabel('scan time (s)');ax.set_ylabel('(observed + alias×PERIOD − D prediction) / SD\nsymlog; not a calibrated z-test')
            ax.grid(alpha=.2)
            ex=evaxes[0,row]
            if result and discovery:
                comparison=result['comparison']
                for offset,model in enumerate(('same','mixed')):
                    x=col*3+offset
                    point=comparison.get(model+'_raw_conditional_objective')
                    bounds=comparison.get(model+'_conditional_log_evidence_bounds')
                    if point is not None:ex.plot(x,point,'o',color='#286f9f' if model=='same' else '#b9563b')
                    if bounds is not None:ex.vlines(x,-2*bounds[1],-2*bounds[0],color='black',lw=2)
                ex.text(col*3+.5,.97-col*.08,arm+': '+str(comparison.get('winner') or 'unproved'),
                    ha='center',transform=ex.get_xaxis_transform(),fontsize=9)
            elif discovery:
                for offset,partial in enumerate((primary,mixed)):
                    if partial and partial.get('objective') is not None:
                        ex.plot(col*3+offset,partial['objective']-discovery['objective'],'o',
                            markerfacecolor='none' if offset==0 else '#b9563b',markeredgecolor='#286f9f' if offset==0 else '#b9563b')
                ex.text(col*3+.5,.97-col*.08,arm+': budget-limited pair\nsame: primary checkpoint only',
                    ha='center',transform=ex.get_xaxis_transform(),fontsize=8)
            ex.set_xticks([0,1,3,4],['c0 same','c0 mixed','fit same','fit mixed'],rotation=25)
            ex.set_title(label+' conditional evidence (D denominator common)')
            ex.set_ylabel('−2 log conditional evidence\npoints and full conditional bounds')
            ex.set_yscale('symlog',linthresh=1.);ex.grid(alpha=.2)
    diagaxes[0].set_title('D-only phase posterior quadrature');diagaxes[0].set_xlabel('phase (s)');diagaxes[0].set_ylabel('density estimate')
    diagaxes[1].set_title('D-only alias probabilities');diagaxes[1].set_xlabel('alias in original track gauge');diagaxes[1].set_ylabel('probability')
    diagaxes[2].set_title('D-only latent pulls, mean ± posterior SD');diagaxes[2].set_xticks(range(4),['shape1','shape2','shape3','Dconst/300Hz'])
    diagaxes[2].axhline(0,color='black',lw=.5)
    for ax in diagaxes:ax.legend(fontsize=8);ax.grid(alpha=.2)
    diagnostic.suptitle('Conditional model diagnostics; quadrature stability is not a certified moment error',fontsize=11)
    diagnostic.tight_layout();diagnostic.savefig(HERE/'D_posterior.png',dpi=160);plt.close(diagnostic)
    predictions.suptitle('Both complete witnesses against CH5-only57450 prediction: all9alias images retained',fontsize=12)
    predictions.tight_layout(rect=(0,0,1,.96));predictions.savefig(HERE/'witness_predictions.png',dpi=160);plt.close(predictions)
    evidence.suptitle('Shared57450 versus Dphysical/Wpolynomial; no sum of overlapping folds',fontsize=12)
    evidence.tight_layout(rect=(0,0,1,.93));evidence.savefig(HERE/'conditional_evidence.png',dpi=160);plt.close(evidence)
    with (HERE/'conditional_table.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    execution=read(RUN/'execution.json')
    write('summary.json',dict(rows=rows,D_posterior=posterior_summary,
        selected_contexts=4,complete_contexts=sum(r['status']=='complete' for r in rows),
        proved_contexts=sum(r['order_proved'] for r in rows),
        scientific_seconds_including_preserved_harness_failure=execution['scientific_seconds'],
        source_RF_seal_sha256=sha(RUN/'RF_seal.json'),protocol_sha256=sha(RUN/'protocol.json'),
        position_fits=0,GPS_used=False,operational_identity_assignment=False,calibrated_moment_band=False))
    files=['report.py','summary.json','conditional_table.csv','D_posterior.png','witness_predictions.png','conditional_evidence.png']
    write('report_seal.json',dict(files={name:sha(HERE/name) for name in files},RF_seal_sha256=sha(RUN/'RF_seal.json')))
    print(json.dumps(dict(rows=rows,seconds=execution['scientific_seconds']),indent=2))


if __name__=='__main__':main()
