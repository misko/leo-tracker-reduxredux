"""Render the unchanged DBG01 atlas and recovery tables for017."""

from pathlib import Path
import shutil
import tarfile
import matplotlib.pyplot as plt
import numpy as np
import report_ds23_dbg01_iteration_016 as renderer
import probe_ds23_iteration017_recovery as binding
import probe_ds23_native_augmented_family as native
import inventory_ds23_residual_concentration as concentration
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha


def configure():
    renderer.binding=binding;renderer.runner=binding.runner;renderer.paths=binding.paths.paths
    renderer.RAW=binding.runner.RAW;renderer.OUT=ROOT/'reports/2026_10_23_ds23_dbg01_iteration_017';renderer.ITERATION=17
    renderer.INCLUDE_INDEPENDENT=True;renderer.METHODS=['Incumbent','Graph recovery','Persistent temporal','Independent predictive','Extra curve']
    renderer.SOURCES=['run_ds23_dbg01_iteration_017.py','probe_ds23_iteration017_recovery.py','audit_ds23_iteration017_recovery.py','audit_ds23_iteration016_recovery.py','ds23_distributed_polynomial_curvature.py','report_ds23_dbg01_iteration_016.py',Path(__file__).name]
    renderer.TESTS=['test_ds23_dbg01_iteration_017.py','test_ds23_iteration017_recovery.py','test_ds23_iteration017_report_binding.py']


def finalize():
    configure();out=renderer.OUT;common=renderer.common;common.OUT=out;common.RAW=renderer.RAW
    assert read(native.OUT/'execution.json')['all_passed'];assert read(native.OUT/'independent_nomination_audit.json')['all_passed']
    nominations=[];trials=[];audits=[]
    for case in read(native.OUT/'protocol.json')['cases']:
        saved=read(native.OUT/(case+'.json'))
        if not saved['eligible']:continue
        rr=saved['nominations'];fig,axes=plt.subplots(1,3,figsize=(18,5),layout='constrained')
        axes[0].bar(range(len(rr)),[r['score'] for r in rr],color=['C0' if r['norad']==saved['target_norad'] else 'C1' for r in rr]);axes[0].set(xticks=range(len(rr)),xticklabels=[str(r['norad']) for r in rr],ylabel='Family-excluded predictive score',title=f"{len(saved['held_IDs'])} original+new held points");axes[0].tick_params(axis='x',rotation=45)
        for r in rr:nominations.append(dict(case=case,original_norad=saved['target_norad'],norad=r['norad'],score=r['score'],phase_s=r['phase_s'],phase_qualified=r['qualified'],conditional_RMS_hz=r['conditional_RMS_hz'],held_points=len(saved['held_IDs']),new_predictive_points=saved['new_target_points']))
        for k,trial in enumerate(saved['trials']):
            for j,arm in enumerate(['c0','fitted_c']):
                s=trial['arms'][arm];null=saved['null_arms'][arm];x=k+(j-.5)*.3
                axes[1].bar(x,trial['RF_gains'][arm],width=.28,color=f'C{j}',label=arm if k==0 else None)
                axes[2].scatter([0+j*.12,1+j*.12],[position_error(null['endpoint_latlon']),position_error(s['endpoint_latlon'])],c=f'C{j}',s=60)
                trials.append(dict(case=case,arm=arm,original_norad=saved['target_norad'],candidate_norad=trial['candidate_norad'],RF_gain=trial['RF_gains'][arm],penalty=trial['search_penalty'],paired_valid=trial['paired_valid'],accepted=trial['accepted'],parent_error_km=position_error(null['endpoint_latlon']),alternative_error_km=position_error(s['endpoint_latlon']),parent_IDs_preserved=trial['all_parent_accepted_IDs_preserved'][arm]))
        axes[1].axhline(2*np.log(2),c='crimson',ls='--');axes[1].set(xticks=range(len(saved['trials'])),xticklabels=[str(t['candidate_norad']) for t in saved['trials']],ylabel='RF gain vs unchanged persistent parent',title='Positive gain required in both arms');axes[1].legend(fontsize=8)
        axes[2].set(xticks=[.06,1.06],xticklabels=['Parent','Rejected alternative'],ylabel='Position error (km), report-only')
        for ax in axes:ax.grid(alpha=.2)
        fig.suptitle(case+f" · largest new-owner family {saved['target_norad']} selected by RF point count alone\nAlternative loses hundreds of RF score units and original gates; influential family is not proved incorrectly identified")
        fig.savefig(out/'figures'/(case+'_native_augmented_family.png'),dpi=145);plt.close(fig)
        audits.extend(saved['independent_endpoint_checks'])
        if case!='DS23-0087':continue
        data,_,_=native.parent(case);lookup={o['observation_id']:o for o in data['observations']};members=saved['held_members'];original=next(r for r in rr if r['norad']==saved['target_norad']);alternative=next(r for r in rr if r['norad']==saved['trials'][0]['candidate_norad'])
        fig,axes=plt.subplots(len(members),2,figsize=(15,3.3*len(members)),squeeze=False,layout='constrained');start=0
        for axs,member in zip(axes,members,strict=True):
            n=member['points'];sl=slice(start,start+n);start+=n;ids=member['observation_ids'];t=np.array([lookup[o]['time_s'] for o in ids]);raw=np.array([lookup[o]['measured_cfo_hz'] for o in ids]);axs[0].scatter(t,raw/1000,c='black',s=18,label='All held original GLRT')
            track=data['scan'].tracks[member['track_index']];use=np.array([o in set(ids) for o in track['observation_ids']]);values=np.asarray(track['values'])[use]
            for label,offer in [('68562',original),('54831 alternative',alternative)]:
                residual=np.asarray(offer['residual_hz'])[sl]
                for k,run in enumerate(np.split(np.arange(n),np.flatnonzero(abs(np.diff(raw-values))>1e-5)+1)):
                    axs[0].plot(t[run],(raw-residual)[run]/1000,label=label+' conditional prediction' if k==0 else None)
                axs[1].plot(t,residual,'.-',label=label)
            axs[0].set(title=f"{member['kind']} RX{member['receiver']} CH{member['channel']} · {n} points",ylabel='Native GLRT CFO (kHz)');axs[1].set(ylabel='Nomination conditional residual (Hz)');axs[1].axhline(0,c='gray')
            for ax in axs:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
        fig.suptitle('DS23-0087 · entire68562 evidence:49 original curved +27 newly recovered predictive points\nCausal orbit + radio/fragment conditional prediction. Full family excluded from calibration prior; no GPS or following TLE')
        fig.savefig(out/'figures'/'DS23-0087_family_CFO_and_residual_context.png',dpi=145);plt.close(fig)
    for name,rows in [('native_family_nominations',nominations),('native_family_trials',trials),('native_family_endpoint_audits',audits)]:renderer.figures.csv_write(out/'tables'/(name+'.csv'),rows)
    assert read(concentration.OUT/'execution.json')['all_passed'];rf=[]
    for path in sorted(concentration.OUT.glob('DS23*.json')):
        rf.extend(dict(case=path.stem,**{k:v for k,v in r.items() if k not in ['observation_ids','times','residual_hz','sigma_hz']}) for r in read(path)['rows'])
    renderer.figures.csv_write(out/'tables/residual_concentration.csv',rf)
    selected=[r for r in rf if r['arm']=='fitted_c' and r['points']>=12];cases=read(concentration.OUT/'protocol.json')['cases'];fig,axes=plt.subplots(1,2,figsize=(17,5),layout='constrained')
    for k,case in enumerate(cases):
        subset=[r for r in selected if r['case']==case];axes[0].bar(k,sum(r['maximum_normalized_energy_fraction']>=.5 for r in subset),color='C1' if case in ['DS23-0075','DS23-0087'] else 'C0')
    axes[0].set(xticks=range(len(cases)),xticklabels=[c[5:] for c in cases],ylabel='Curves with one point ≥50% of normalized energy',title='Descriptive flag, not a deletion or significance gate');axes[0].tick_params(axis='x',rotation=60)
    axes[1].scatter([r['points'] for r in selected],[r['maximum_normalized_energy_fraction'] for r in selected],s=12,alpha=.6);axes[1].axhline(.5,c='crimson',ls='--');axes[1].set(xlabel='Active original calibration points in curve',ylabel='Largest RF-sigma-normalized residual energy fraction')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('RF-only residual inventory · original incumbent, fitted c · engineering2 + frozen random20\nNo new spatial fit, source/point deletion, model selection or accuracy-based threshold tuning')
    fig.savefig(out/'figures/residual_concentration_inventory.png',dpi=145);plt.close(fig)
    example=next(r for r in read(concentration.OUT/'DS23-0087.json')['rows'] if r['arm']=='fitted_c' and 'RX1-CH3-T000' in r['component']);fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained');t=np.array(example['times']);res=np.array(example['residual_hz']);ix=example['maximum_raw_index'];axes[0].plot(t,res,'.-');axes[0].scatter(t[ix],res[ix],c='crimson',s=80,label='Largest residual; retained');axes[0].axhline(0,c='gray');axes[0].set(xlabel='Scan time (s)',ylabel='Original joint conditional residual (Hz)');axes[0].legend(fontsize=8)
    axes[1].bar(['All33 points','Other32, diagnostic only'],[example['RMS_hz'],example['diagnostic_RMS_without_maximum_hz']]);axes[1].set(ylabel='RMS (Hz) at same unchanged endpoint');axes[1].grid(axis='y',alpha=.2)
    fig.suptitle('DS23-0087 RX1 CH3 T000 /68562 · original group precision0.1296 applies to all33 points\nLast point contributes76.5% raw /74.9% normalized energy. Not proof of a bad point; no measurement removed')
    fig.savefig(out/'figures/DS23-0087_residual_energy_concentration.png',dpi=145);plt.close(fig)
    shutil.copyfile(native.OUT/'independent_nomination_audit.json',out/'evidence/native_family_nomination_audit.json')
    for name in ['probe_ds23_native_augmented_family.py','audit_ds23_native_augmented_family.py','inventory_ds23_residual_concentration.py',Path(__file__).name]:shutil.copyfile(ROOT/'tools'/name,out/'source/tools'/name)
    shutil.copyfile(ROOT/'tests/analysis/test_ds23_native_augmented_family.py',out/'source/tests/test_ds23_native_augmented_family.py')
    shutil.copyfile(ROOT/'tests/analysis/test_ds23_residual_concentration.py',out/'source/tests/test_ds23_residual_concentration.py')
    common.archive(read(renderer.RAW/'protocol.json')['cases']);common.gallery();p=out/'FIGURES.md';p.write_text(p.read_text().replace('# Iteration011 figure inventory','# Iteration017 figure inventory',1))
    target=out/'evidence/residual_concentration.tar.gz';files=sorted(concentration.OUT.glob('*.json'))
    with tarfile.open(target,'w:gz') as archive:
        for path in files:archive.add(path,arcname=path.name,recursive=False)
    if target.stat().st_size>=45*1024**2:raise ValueError('split RF inventory archive')
    manifest=read(out/'evidence/archive_manifest.json');manifest.append(dict(file=str(target.relative_to(out)),bytes=target.stat().st_size,sha256=sha(target),source_files=len(files)));write(out/'evidence/archive_manifest.json',manifest)
    evaluation=read(out/'evidence/evaluation.json');evaluation['RF_concentration_diagnostic']=dict(curves_at_least12points=len(selected),curves_at_least50percent_normalized_energy=sum(r['maximum_normalized_energy_fraction']>=.5 for r in selected),no_new_noise_model_or_position_fit=True);write(out/'evidence/evaluation.json',evaluation)
    write(out/'evidence/source_hashes.json',{str(p.relative_to(out)):sha(p) for p in (out/'source').rglob('*.py')})


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--finalize',action='store_true');args=parser.parse_args()
    if args.finalize:finalize()
    else:configure();renderer.main()
