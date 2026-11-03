"""Audit corrected RF-clock comparisons; visualize measured RF eligibility."""

from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_predictive_subsets import realize_predictive_subsets,assert_realized_predictive_membership
from ds23_radio_calibration_factor import make_calibrated_problem,attach_calibrated_predictive
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_frequency_events import summary
from probe_ds23_realized_clock_controls import SOURCE as CLOCK_SOURCE,OUT as CLOCK_OUT
from select_ds23_differential_information import OUT
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis


def clock_case(case):
    scan,node,_,powers,means,hyper,_,signed,_=context_signed(case)
    plan=read(CLOCK_SOURCE/case/'plan.json');selected=plan['plans']['strict'];keep=np.asarray(selected['keep'],bool)
    augmented,entries,receipt=realize_predictive_subsets(scan,selected['entries'])
    ids=assert_realized_predictive_membership(augmented,entries,selected['disjoint']['excluded_probe_graph_ids'])
    audits=[];rows=[]
    for noise in ['control','bootstrap','plus_radio']:
        r=read(CLOCK_OUT/(case+'_'+noise+'.json'));assert r['status']=='complete'
        pair={};maximum=0.
        for arm,saved in r['arms'].items():
            p=make_calibrated_problem(augmented,node,keep,arm,np.array(saved['phase_reference']),powers,means,hyper,[],r['measurements'],projected_receiver_basis)
            attach_calibrated_predictive(p,entries,powers);x=np.array(saved['endpoint_east_north_km'])
            value=p.calculate(x);difference=abs(value['negative_twice_elbo']-saved['negative_twice_elbo']);maximum=max(maximum,difference)
            assert difference<1e-5 and len(value.get('linear_raw_prediction_residual_hz',[]))==len(ids)
            current=summary(p,x,entries);current['final_phase_change_s']=saved['final_phase_change_s']
            assert current['linear_calibration_max_difference']==0;pair[arm]=current
        assert valid(pair)
        audits.append(dict(case=case,noise=noise,maximum_normalized_objective_replay_difference=maximum,
            physical_predictive_rows=len(ids),declared_predictive_rows=sum(e['points'] for e in entries),
            omitted_source_points=sum(r['original_points']-r['retained_points'] for r in receipt),
            actual_RF_GLRT_data_disjoint=True,original_curved_and_predictive_gates_pass=True,
            source_result_sha256=sha(CLOCK_OUT/(case+'_'+noise+'.json'))))
        # Evaluation GPS is used only after the numerical row and gate audits.
        from report_algo02_ds23 import position_error
        for arm,saved in r['arms'].items():
            old=r['source_old_arms'][arm];original=signed['policy_arms'][arm]
            rows.append(dict(case=case,noise=noise,arm=arm,paired_valid=r['paired_valid'],
                original_error_km=position_error(original['endpoint_latlon']),legacy_error_km=position_error(old['endpoint_latlon']),
                corrected_error_km=position_error(saved['endpoint_latlon']),legacy_RMS_hz=old['RMS_hz'],corrected_RMS_hz=saved['RMS_hz'],
                RF_measurements=len(r['measurements']),physical_predictive_points=len(ids)))
    return audits,rows


def main():
    rf=read(OUT/'RF_pilot.json');rf_audit=read(OUT/'RF_independent_audit.json');membership=read(OUT/'predictive_membership_audit.json')
    assert membership['all_terminal'] and membership['cases']==410
    audits=[];rows=[]
    for case in ['DS23-0154','DS23-0216']:
        a,r=clock_case(case);audits.extend(a);rows.extend(r)
    write(CLOCK_OUT/'independent_audit_and_evaluation.json',dict(audits=audits,rows=rows,
        all_endpoints_replayed=True,all_actual_numeric_predictive_rows_match_declared_IDs=True,
        no_full_DS23_or_generalization_gain_claim=True))
    with (CLOCK_OUT/'position_comparison.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    names=['DS23-0154','DS23-0216'];offsets={'control':-.2,'bootstrap':0.,'plus_radio':.2}
    colors={'control':'#777777','bootstrap':'#168b91','plus_radio':'#df801b'}
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        for i,case in enumerate(names):
            selected=[r for r in rows if r['case']==case and r['arm']==arm]
            ax.scatter(i-.32,selected[0]['original_error_km'],color='black',marker='*',s=90,label='Original full-GLRT incumbent' if i==0 else None)
            for r in selected:
                x=i+offsets[r['noise']];color=colors[r['noise']]
                ax.plot([x-.035,x+.035],[r['legacy_error_km'],r['corrected_error_km']],color=color)
                ax.scatter(x-.035,r['legacy_error_km'],facecolors='none',edgecolors=color,marker='o',label=r['noise']+' · legacy rows' if i==0 else None)
                ax.scatter(x+.035,r['corrected_error_km'],color=color,marker='s',label=r['noise']+' · corrected rows' if i==0 else None)
        ax.set_xticks(range(2),['0154','0216']);ax.set(title=arm,xlabel='DS23 scan',ylabel='Position error (km)');ax.grid(alpha=.2)
    axes[1].legend(fontsize=7,loc='best');fig.suptitle('RF-clock control correction · declared subsets now select the actual predictive samples')
    fig.tight_layout();fig.savefig(OUT/'clock_membership_correction.png',dpi=160);plt.close(fig)
    ordered=sorted(rf['rows'],key=lambda r:(r['case'],r['probe']));x=np.arange(len(ordered))
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for i,r in enumerate(ordered):
        color='#168b91' if r.get('RF_qualified') else '#c54e55'
        axes[0].scatter(i,r['declared_sigma_hz'],color=color)
        axes[1].scatter(i,r['full']['difference_hz']-(r['job']['first']['cfo_hz']-r['job']['second']['cfo_hz']),color=color)
    for ax in axes:
        ax.set_xticks(x,[r['case'].split('-')[1]+'/'+str(r['probe']) for r in ordered],rotation=65,fontsize=8);ax.grid(alpha=.2)
    axes[0].set_yscale('log');axes[0].set(ylabel='Conditional contrast SD (Hz)',title='Three of nine pass original RF checks')
    axes[1].set(ylabel='Measured contrast change from native seed (Hz)',title='Actual saved-IQ remeasurement; no location truth')
    fig.suptitle('Information-selected RF contrasts · teal passes RF checks; red fails\nCarrier-epoch approximation remains unresolved for the three passing probes',fontsize=11)
    fig.tight_layout();fig.savefig(OUT/'targeted_RF_diagnostics.png',dpi=160);plt.close(fig)
    selection=read(OUT/'target_selection.json');before=read(OUT/'inventory.json')
    write(OUT/'current_analysis_receipt.json',dict(previous_probes=before['probes'],previous_unique_curved_pairs=before['unique_pairs'],
        new_target_probes=selection['selected_probes'],cases_with_targets=selection['cases_with_targets'],
        RF_pilot_probes=len(rf['rows']),RF_checks_pass=rf['RF_qualified'],
        RF_checks_and_epoch_controls_pass=sum(r['RF_qualified'] and r['epoch_linearization_qualified'] for r in rf_audit['rows']),
        RF_fit_replays=sum(r['replayed_fits'] for r in rf_audit['rows']),corrected_clock_endpoint_arms=12,
        original_ALGO02_predictive_mismatches=membership['original_scans_with_mismatches'],
        combined_recovery_predictive_mismatches=membership['combined_scans_with_mismatches'],
        no_real_benchmark_change=True,no_new_RF_collection=True,no_GPS_in_inference=True,
        figures=['targeted_RF_diagnostics.png','clock_membership_correction.png']))
    print([(r['case'],r['noise'],r['arm'],r['legacy_error_km'],r['corrected_error_km']) for r in rows],flush=True)


if __name__=='__main__':main()
