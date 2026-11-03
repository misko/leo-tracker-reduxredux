"""Report negative controls and family influence for the largest remaining errors."""

import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ablate_ds23_learned_prior_families import OUT as INFLUENCE
from probe_ds23_learned_prior_restarts import OUT as RESTARTS,STARTS
from probe_ds23_frequency_rate import OUT as RATE
from probe_ds23_learned_family_replacements import OUT as REPLACEMENTS
from report_algo01_ds23_sample import position_error,REFERENCE
from run_algo01_ds23_sample import ROOT,read,write,sha
from prototype_dsx01_continuous_position import CENTER
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem
from probe_ds23_causal_phase_mean import forecast_phase_mean
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from probe_algo01_0217_improvements import changed_node
from run_algo01_ds23_sample import final_scan,OUT as SOURCE
from leo.analysis.research.retained_track_likelihood import PERIOD

OUT=ROOT/'reports/2026_10_18_ds23_remaining_failures'
CASES=('DS23-0257','DS23-0202','DS23-0273')


def challenger_plot(replacement):
    case='DS23-0257';scan=final_scan(case);original=read(SOURCE/case/'result.json')
    source=read(LEARNED/(case+'.json'));model=source['hyperparameters_from_pre_RF_TLE_only']
    keep=np.array(replacement['fixed_mask'],bool)
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    old_node=original['final_node'];new_node=changed_node(scan,old_node,replacement['best']['changes'])
    records={'63070':source['results']['mean_and_distribution']['arms']['c0'],
             '48482':replacement['best_paired_finalists']['c0']}
    selected=[c['row_index'] for c in replacement['best']['changes']]
    fig,axes=plt.subplots(2,len(selected),figsize=(11,6),squeeze=False,constrained_layout=True)
    diagnostics={}
    for method,node,color in [('63070',old_node,'tab:blue'),('48482',new_node,'tab:orange')]:
        record=records[method];base=problem(scan,node,'c0',keep)
        _,receipts=phase_widths(scan,base.labels);mu=forecast_phase_mean(receipts,model['shrinkage'])
        reference=np.zeros(len(mu))
        for h in record['history']:
            p=make_problem(scan,node,keep,'c0',reference,weights,mu,model['multiplier'],model['nu'])
            xy=np.array(h['fit']['parameters']);reference=np.clip(p.state(xy)['phases'][p.labels],-15,15)
        c=p.calculate(xy);state=p.state(xy)
        nb,ns=p.hardware.shape[1],p.smooth.shape[1];start=nb+ns
        a=c['latent_coefficient'];terms=a*a*c['coefficient_prior_precision']
        prior=dict(hardware=float(terms[:nb].sum()),smooth=float(terms[nb:start].sum()),
            phase=float(terms[start:start+len(p.labels)].sum()),physical_orbit=float(terms[start+len(p.labels):-len(p.members)].sum()),
            fragment=float(terms[-len(p.members):].sum()))
        diagnostics[method]=dict(negative_twice_elbo=c['negative_twice_elbo'],score=record['score'],
            data_cost=c['quadratic']-sum(prior.values()),prior_cost=prior,logvolume=c['logvolume'],
            noise_gamma=c['noise_gamma_cost'],prior_gamma=c['prior_gamma_cost'],normalization=c['normalization_constant'],
            state=state,prior_phase_sigma_s=p.phase_sigma,phase_label_norads=[int(scan.norads[j]) for j in p.labels],
            score_replay_difference=float(p.residual(xy)@p.residual(xy)-record['score']))
        for col,k in enumerate(selected):
            i,sl=p.members[k],p.slices[k];track=scan.tracks[i];active=keep[sl]
            common_alias=old_node['aliases'][k]
            observed=track['values'][active]+common_alias*PERIOD
            predicted=p.values[sl][active]-c['conditional_residual_hz'][sl][active]
            predicted-=(node['aliases'][k]-common_alias)*PERIOD
            axes[0,col].scatter(track['times'][active],observed,s=7,c='gray',label='GLRT' if method=='63070' else None)
            axes[0,col].plot(track['times'][active],predicted,c=color,label=method)
            axes[1,col].plot(track['times'][active],c['conditional_residual_hz'][sl][active],'.-',c=color,ms=3,label=method)
            axes[0,col].set(title=f"RX{track['receiver']} CH{track['channel']} · {active.sum()} points",ylabel='Measured / modeled CFO (Hz)')
            axes[1,col].set(xlabel='Scan time (s)',ylabel='Conditional residual (Hz)');axes[1,col].axhline(0,c='black',lw=.5)
    for ax in axes.flat:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Scan257: one entire cross-receiver family replacement · each fit at its RF endpoint\nSame observations, alias convention and nuisance priors; c=0')
    fig.savefig(OUT/'63070_vs_48482.png',dpi=170);plt.close(fig)
    write(OUT/'challenger_decomposition.json',diagnostics)
    return diagnostics


def run():
    OUT.mkdir(parents=True,exist_ok=True);rows=[];restarts=[]
    fig,axes=plt.subplots(2,3,figsize=(16,9),constrained_layout=True)
    reference_xy=[(REFERENCE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),(REFERENCE[0]-CENTER[0])*111]
    for col,case in enumerate(CASES):
        document=read(INFLUENCE/(case+'.json'));r=read(RESTARTS/(case+'.json'))
        assert len(r['records'])==len(STARTS) and not r['GPS_used']
        selected=list(document['results'].items())
        baseline=position_error(document['results']['baseline']['arms']['c0']['endpoint_latlon'])
        ax=axes[0,col]
        for arm,offset,color in [('c0',-.15,'tab:blue'),('fitted_c',.15,'tab:orange')]:
            values=[position_error(v['arms'][arm]['endpoint_latlon']) for _,v in selected]
            ax.plot(np.arange(len(selected))+offset,values,'.-',color=color,label=arm)
        ax.axhline(.5,color='crimson',ls='--',label='0.5 km target')
        ax.set_xticks(range(len(selected)),[k.replace('minus_family_','−').replace('minus_','−') for k,_ in selected],rotation=90,fontsize=7)
        ax.set(title=case+' · deletion controls',ylabel='Position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=7)
        for name,result in selected:
            for arm,fit in result['arms'].items():
                rows.append(dict(case=case,control=name,arm=arm,error_km=position_error(fit['endpoint_latlon']),
                    calibration_points=fit['active_points'],RMS_hz=fit['RMS_hz'],valid=result['valid']))
        scores=[v['arms']['c0']['score'] for v in r['records']]
        endpoints=np.array([v['arms']['c0']['endpoint_east_north_km'] for v in r['records']])
        spread=float(np.max(np.linalg.norm(endpoints-endpoints[0],axis=1)))
        restarts.append(dict(case=case,starts=len(r['records']),endpoint_spread_km=spread,
            score_spread=max(scores)-min(scores),all_gates_pass=all(v['paired_gates_pass'] for v in r['records']),
            baseline_error_km=baseline,RF_chosen_index=r['chosen']))
        ax=axes[1,col]
        for number,record in enumerate(r['records']):
            start=np.array(record['start']);ax.scatter(*start,facecolors='none',edgecolors='black',s=35,zorder=4)
            for arm,color in [('c0','tab:blue'),('fitted_c','tab:orange')]:
                trajectory=np.array([record['start']]+[h['fit']['parameters'] for h in record['arms'][arm]['history']])
                ax.plot(trajectory[:,0],trajectory[:,1],'.-',color=color,alpha=.28,lw=.6)
                ax.scatter(*record['arms'][arm]['endpoint_east_north_km'],marker='x',c=color,s=65,zorder=5,label=arm+' final' if number==0 else None)
        ax.scatter(*reference_xy,marker='*',c='crimson',s=130,label='Reference: evaluation only',zorder=6)
        ax.add_patch(plt.Circle((0,0),10,fill=False,color='gray',ls='--',lw=.7))
        ax.set(xlabel='East from regional center (km)',ylabel='North (km)',title=case+' · fixed-association prior control',xlim=(-12.5,12.5),ylim=(-12.5,12.5),aspect='equal')
        ax.grid(alpha=.2);ax.legend(fontsize=6,loc='upper left')
    fig.suptitle('Remaining failures: family influence and regional restarts\nLines join phase-round endpoints; inner optimizer paths are not shown')
    fig.savefig(OUT/'influence_and_restarts.png',dpi=180);plt.close(fig)
    with (OUT/'influence.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    frequency=[]
    for case in ('DS23-0217','DS23-0257'):
        d=read(RATE/(case+'.json'))
        for name,result in d['results'].items():
            for arm,fit in result['arms'].items():
                frequency.append(dict(case=case,sigma=name,arm=arm,error_km=position_error(fit['endpoint_latlon']),
                    RMS_hz=fit['RMS_hz'],calibration_points=fit['active_points'],valid=result['valid']))
    with (OUT/'frequency_rate.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(frequency[0]),lineterminator='\n');w.writeheader();w.writerows(frequency)
    replacement=read(REPLACEMENTS/'DS23-0257.json')
    challenger=challenger_plot(replacement)
    write(OUT/'summary.json',dict(restarts=restarts,family_search=dict(singles=len(replacement['single_trials']),
        joint=len(replacement['joint_trials']),accepted=replacement['accepted_over_incumbent'],truncated=replacement['joint_budget_truncated']),
        no_GPS_control_selection=True,target_met=False,report_source_sha256=sha(Path(__file__))))
    table=['| Scan | Learned-prior error c0 / fitted-c, km | Best single-family deletion c0 / fitted-c, km |',
           '|---|---:|---:|']
    for case in CASES:
        d=read(INFLUENCE/(case+'.json'))['results'];base=d['baseline']['arms']
        best=min([v for k,v in d.items() if k.startswith('minus_family')],key=lambda v:position_error(v['arms']['c0']['endpoint_latlon']))['arms']
        table.append(f"| {case} | {position_error(base['c0']['endpoint_latlon']):.3f} / {position_error(base['fitted_c']['endpoint_latlon']):.3f} | {position_error(best['c0']['endpoint_latlon']):.3f} / {position_error(best['fitted_c']['endpoint_latlon']):.3f} |")
    old,new=challenger['63070'],challenger['48482']
    differences={'Conditional data cost':new['data_cost']-old['data_cost'],
        'Gaussian hardware/smooth/orbit/fragment priors':sum(v for k,v in new['prior_cost'].items() if k!='phase')-sum(v for k,v in old['prior_cost'].items() if k!='phase'),
        'Phase prior quadratic':new['prior_cost']['phase']-old['prior_cost']['phase'],
        'Nuisance volume':new['logvolume']-old['logvolume'],
        'Noise Gamma cost':new['noise_gamma']-old['noise_gamma'],
        'Phase Gamma cost':new['prior_gamma']-old['prior_gamma'],
        'Normalizing constants':new['normalization']-old['normalization']}
    breakdown=['| Challenger minus incumbent | RF loss units |','|---|---:|']
    breakdown.extend(f'| {k} | {v:+.3f} |' for k,v in differences.items())
    text='''# DS23: remaining failures under the causal learned prior

No single-family deletion fixes these three largest remaining c0 errors.
The best deletions below are **GPS oracle diagnostics**, not an implementable
selection policy. Every tested deletion, including regressions, is in the CSV.

TABLE

![Family influence and regional restarts](influence_and_restarts.png)

## Deletion controls

Each control starts with the learned primary rule's final quality-gated mask,
then deliberately removes one family or receiver. Labels, alias integers,
radio noise, causal priors and cold regional-center start are unchanged.
Any subsequent gate failure removes that component in both c arms. Existing
physical-mode support cascades remain active; counts can fall further than
the deliberate deletion. This measures sensitivity, not proof of a bad label.
The final masks, gate reasons, states and five phase histories are retained.

## Regional restarts

Use 13 fixed regional starting points: center, ±5/±10 km on each axis,
and four (±5,±5) km corners. The 10 km disk is centered at the declared
regional center, not at supplied GPS. All starts keep exactly the same
observations, weights, satellite labels, aliases and learned prior. Five
phase-reference rounds and 48 position steps per round are matched. No
observations are trimmed within this control. RF c0 loss selects a branch
only among pairs passing all original gates. This specifically tests whether
the new Student phase prior creates another accessible continuous minimum;
it is **not** a full association-reselecting pipeline restart experiment.
The plot connects successive phase-round endpoints; it does not display
each inner optimizer step. Red stars are evaluation markers only.

All13 starts reach the same endpoint on each of the three scans, to numerical
precision (maximum spread below3e-8 km). This rules out these regional starting
points as a remedy under fixed labels; it does not prove global optimality
over identities, orbit parameters or a different physical model.

## Additional receiver mode

Test one receiver-specific linear drift proportional to RF within each band,
in addition to existing band/receiver mean drift and smooth terms. Its
Gaussian prior standard deviation is 0,0.25 or1 Hz/s/GHz. Fixed band centers
come from distinct recorded RFs, without frequency residuals or GPS. The
mode is sigma*(t−150)*(RF−band_center)/GHz Hz and carries the same marginal
complexity penalty as other nuisance terms. The extra receiver-basis and
seed-state dimensions are expanded consistently. The zero mode reproduces
the comparator to about1e-8 km and1e-10 RF-loss units.

It has little effect: at c0,217 changes1.025→1.009 km and257 remains3.722 km.
Fitted-c changes0.869→0.846 km and3.699→3.695 km. All gates pass. This small
RF-dependent linear rate is not a sufficient explanation of the large error;
no new defaults are selected from these two known-site results.

## Broader identities

The257 search screens the complete original causal catalogue at its RF endpoint,
the regional center and four nearby anchors. It proposes two whole-family
alternatives per original family, then pairs/triples the RF-best six distinct
original-family changes. This permits several entire families to change at
once. Proposal screening approximates phase+constant with a Gaussian; every
trial is refit with the full learned prior and physical modes. Uniqueness is
not claimed. Observations and likelihood powers stay fixed for this controlled
identity test. Score by normalized generalized ELBO, not incomparable raw
prior scores; both arms must pass gates before accepting an RF improvement.
The summary records actual proposal counts and budget truncation. It is a
diagnostic, not a promoted association policy or an exhaustive identity proof.

All26 single-family and35 simultaneous pair/triple proposals were completed
within114.3s. One single-family proposal passes gates; no joint proposal does.
None wins the RF objective. The passing alternative replaces63070 with48482
on two RX/channel fragments. It gives1.083/0.831km instead of3.722/3.699km,
but costs15.268 more normalized generalized RF-loss units at c0. It is
therefore rejected by the declared rule. Its proximity to known GPS is a
diagnostic observation, not identity ground truth or a permitted selection.

![Cross-receiver incumbent and challenger](63070_vs_48482.png)

[Challenger objective decomposition](challenger_decomposition.json) separates
conditional data cost, hardware/smooth/phase/orbit/fragment prior penalties,
nuisance volume, grouped-noise cost and normalizing constants. Each curve
uses its own RF endpoint and joint calibration, with the same observations
and original alias convention. The figure does not isolate satellite shape
from every nuisance term; it shows the two complete fitted explanations.

BREAKDOWN

Most of the15.268-unit disadvantage is phase regularization:5.318 in the
quadratic term plus4.972 in the phase-Gamma term. Conditional data cost adds
only2.804 units. The challenger uses a −5.612s family phase adjustment versus
−0.980s for the incumbent. This identifies a sensitivity of the identity
decision to the causal phase model; it does not establish which identity is
correct. Arbitrarily widening the prior until GPS improves is not a solution.

## Evidence and implications

[All family/receiver controls](influence.csv) · [Rate controls](frequency_rate.csv) ·
[Summary](summary.json).
Raw inputs/outputs: ../2026_10_18_ds23_learned_prior_influence/,
../2026_10_18_ds23_learned_prior_restarts/,
../2026_10_18_ds23_frequency_rate/ and
../2026_10_18_ds23_learned_family_replacements/.

These controls narrow explanations; they do not prove identities or establish
a unique physical cause. Multiple wrong associations, biased causal orbits,
transmitter/receiver clock covariance and insufficiently informative curves
remain possible. The 0.5 km DS23 mean/median goal is not achieved. The next
useful work is independent RF evidence and causal orbit/clock calibration,
followed by frozen-rule validation on untouched scans. No later TLE, GPS
optimization, new RF collection, or QNAP mutation is part of this experiment.
'''.replace('TABLE','\n'.join(table)).replace('BREAKDOWN','\n'.join(breakdown))
    (OUT/'README.md').write_text(text);print('\n'.join(table),flush=True)


if __name__=='__main__':run()
