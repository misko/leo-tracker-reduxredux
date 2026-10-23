"""Replay gate attribution and render completed018 conflict tests; no fitting."""
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import probe_ds23_iteration018_recovery as binding
from run_algo01_ds23_sample import read,write
from report_algo02_ds23 import position_error
from compare_dsx01_frame_joint import conditional_gate
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile,whitening

OUT=Path(__file__).resolve().parents[2]
RAW=binding.runner.RAW


def csv_write(name,rows):
    with (OUT/'tables'/name).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)


def gate_attribution(p,saved,norad):
    x=np.asarray(saved['endpoint_east_north_km']);state=p.state(x);calc=p.calculate(x)
    frequency,elevation=p.conditional_frequency(x);final={r['component']:r for r in saved['gates']['tracks']}
    rows=[];series=[]
    for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        active=p.keep[sl]
        if row['candidate_norad']!=norad or not active.any():continue
        t=p.scan.tracks[i];times=t['times'][active];q=t['rf_hz']/11.5e9
        y=t['values']-p.scan.hardware(t,state['beta'])-q*p.scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        terms=profile(y[active],q*frequency[sl][active],*whitening(times));noise=batch_noise_screen(terms['innovations'],times)
        residual=calc['conditional_residual_hz'][sl][active];conditional=conditional_gate(residual,times)
        gates=dict(rms=bool(terms['rms'][0]<=450),bias=bool(abs(terms['bias'][0])<=3000),
            profile_noise=bool(noise['noise_screen_pass'][0]),conditional_noise=bool(conditional['compatible']),
            alias=bool(int(terms['alias'][0])==alias),elevation=bool(elevation[sl][active].min()>=0))
        passes=all(gates.values());accepted=final[t['key']]['compatible']
        assert not accepted or passes
        rows.append(dict(component=t['key'],norad=norad,points=int(active.sum()),owner=f"RX{t['receiver']} CH{t['channel']}",
            profile_rms_hz=float(terms['rms'][0]),minimum_elevation_deg=float(elevation[sl][active].min()),
            base_gates_pass=passes,final_gate_pass=accepted,rejected_by_support_cascade=bool(passes and not accepted),
            failed_base_gates=';'.join(k for k,v in gates.items() if not v),orbital_modes_enabled=row['candidate_index'] in p.supported,
            conditional_slope_z=conditional['diagnostics']['slope_z'],conditional_step_z=conditional['diagnostics']['maximum_step_z'],conditional_acf1=conditional['diagnostics']['lag1_acf']))
        series.append(dict(component=t['key'],time_s=times,values_hz=t['values'][active],residual_hz=residual))
    return rows,series


def main():
    binding.configure('paths');paths=binding.paths.paths;trials=[];attribution=[];saved_series=[]
    for case in read(RAW/'protocol.json')['cases']:
        d,_,kind,_=paths.parent(case)
        record=read(RAW/'conflict_alternatives'/(case+'.json'))
        for group in record['groups']:
            for trial in group['trials']:
                for arm,saved in trial['arms'].items():
                    target=next(r for r in saved['gates']['tracks'] if r['component']==trial['component'])
                    trials.append(dict(case=case,component=trial['component'],norad=trial['norad'],arm=arm,
                        points=group['points'],paired_valid=trial['paired_valid'],parent_IDs_preserved=trial['parent_IDs_preserved'][arm],
                        position_error_km=position_error(saved['endpoint_latlon']),RMS_hz=saved['RMS_hz'],
                        target_profile_RMS_hz=target['profile_rms_hz'],target_compatible=target['compatible'],
                        conditional_noise_pass=target['conditional_residual_gate']['compatible'],
                        corrected_selection_loss=saved['corrected_selection_loss']))
                    if case=='DS23-0261' and trial['norad']==62146:
                        dd=dict(d,node=trial['node'],keep=np.asarray(trial['mask'],bool),means=np.asarray(trial['means']))
                        p=paths.build(dd,kind,arm,saved['phase_reference']);rows,series=gate_attribution(p,saved,62146)
                        attribution.extend(dict(arm=arm,**r) for r in rows)
                        if arm=='fitted_c':saved_series=series
    csv_write('conflict_alternatives.csv',trials);csv_write('family_gate_attribution.csv',attribution)
    write(OUT/'evidence/family_gate_attribution.json',dict(rows=attribution,series=saved_series,no_new_optimization=True))
    fig,axes=plt.subplots(len(saved_series),2,figsize=(13,9),layout='constrained')
    for axes_row,s in zip(axes,saved_series,strict=True):
        t=np.asarray(s['time_s']);y=np.asarray(s['values_hz']);res=np.asarray(s['residual_hz'])
        label=s['component'].split('-RF')[0].replace('DS23-0261-','')
        row=next(r for r in attribution if r['arm']=='fitted_c' and r['component']==s['component'])
        axes_row[0].scatter(t,y/1000,s=18,c='black',label='All whole-source GLRT')
        axes_row[0].plot(t,(y-res)/1000,c='C1',label='Joint orbit + nuisance prediction')
        axes_row[1].plot(t,res,'.-',c='C3');axes_row[1].axhline(0,c='gray',lw=1)
        reason='Support cascade only' if row['rejected_by_support_cascade'] else row['failed_base_gates']
        axes_row[0].set(title=label,ylabel='Graph-unwrapped CFO (kHz)');axes_row[1].set(title=reason,ylabel='Conditional residual (Hz)')
        for ax in axes_row:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8)
    fig.suptitle('DS23-0261: rejected 62146 addition, fitted c\nThe new CH4 source fails its residual gates; individually passing CH1 sources then lose multi-owner support')
    fig.savefig(OUT/'figures/DS23-0261_family_conflict.png',dpi=145);plt.close(fig)
    family=read(RAW/'single_source_augmented_family/DS23-0261.json')
    nominees=[dict(norad=r['norad'],score=r['score'],phase_s=r['phase_s'],qualified=r['qualified']) for r in family['nominations']]
    csv_write('whole_family_candidates.csv',nominees)
    rows=[]
    for trial in family['trials']:
        for arm,s in trial['arms'].items():rows.append(dict(norad=trial['candidate_norad'],arm=arm,paired_valid=trial['paired_valid'],
            position_error_km=position_error(s['endpoint_latlon']),RMS_hz=s['RMS_hz'],
            RF_gain=trial.get('RF_gains',{}).get(arm,0),accepted=trial.get('accepted',False)))
    csv_write('whole_family_refits.csv',rows)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    axes[0].bar([str(r['norad']) for r in nominees],[r['score'] for r in nominees],color=['C0' if r['qualified'] else 'lightgray' for r in nominees])
    axes[0].set(title='Entire 85-point family held out for nomination',ylabel='Cavity score (lower better)');axes[0].tick_params(axis='x',rotation=45)
    gain=[r['RF_gain'] for r in rows if r['norad']==66399]
    axes[1].bar(['c = 0','fitted c'],gain,color='C3');axes[1].axhline(2*np.log(2),c='green',ls='--',label='Required positive gain')
    axes[1].set(title='Whole-family 66399 vs 62146, matched points',ylabel='RF objective gain (positive better)');axes[1].legend()
    fig.suptitle('DS23-0261: whole-family replacement does not resolve the conflict\nBoth joint fits fail gates; gray nomination bars fail the physical phase constraint')
    fig.savefig(OUT/'figures/DS23-0261_family_replacement.png',dpi=145);plt.close(fig)
    print('Saved',len(trials),'alternative arm rows and',len(attribution),'gate attributions')


if __name__=='__main__':main()
