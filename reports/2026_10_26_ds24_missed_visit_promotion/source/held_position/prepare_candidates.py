"""Freeze coherent-only primary/sensitivity inputs after native/graph seals."""
import copy
from pathlib import Path
import shutil
from position import HERE,REPO,OLD,SOURCE,VARIANTS,read,write,sha,estimate,floored_noise,input_audit
import numpy as np

BROADER=HERE.parent/'broader'
PREVIOUS=OLD/'coherent_application'

def effective(noise,ids):
    return {oid:noise['per_observation_noise_sigma_hz'][oid] if noise['extra_parameter_BIC_gain']>0 else noise['constant_radio_sigma_hz'] for oid in ids}

def reuse_audit(overlays):
    old=read(PREVIOUS/'position_protocol.json');terminal=read(PREVIOUS/'position_final_terminal_seal.json')
    assert terminal['all_terminal'] and terminal['evaluation_now_permitted'] and not terminal['denied_reads']
    assert terminal['inputs_and_first_attempt_artifacts_unchanged']
    assert terminal['original_protocol_sha256']==sha(PREVIOUS/'position_protocol.json')
    continuation=read(PREVIOUS/'engine_continuation_protocol.json')
    assert terminal['continuation_protocol_sha256']==sha(PREVIOUS/'engine_continuation_protocol.json')
    for p,h in dict(old['input_hashes'],**old['source_hashes']).items():assert sha(p)==h,p
    for p,h in continuation['protected_existing_files'].items():assert sha(p)==h,p
    for p,h in terminal['terminal_output_hashes'].items():assert sha(p)==h,p
    current=read(HERE/'baseline_queue/protocol.json')
    checks={'seconds_per_complete_job':240,'BLAS_threads':1,'radio_seed_budget':4,'fully_fitted_RF_branches':3,'phase_rounds':5,'steps_per_round':48,'regional_center':[37.906,-122.545],'box_width_km':25.,'start':[0.,0.]}
    assert all(old[k]==v for k,v in checks.items())
    for p,h in current['sources_sha256'].items():assert sha(p)==h,p
    controls=[]
    for case in ('DS24-0011','DS24-0097'):
        overlay=overlays[case];rows=read(overlay/'observations.json');ids=[o['observation_id'] for o in rows]
        new=set(read(overlay/'new_native_owners.json')['observation_ids'])
        proxy=estimate(read(overlay/'tracks.json'),rows)
        for variant in ('additions_bin_floor','additions_proxy'):
            job=next(j for j in old['jobs'] if j['case']==case and j['variant']==variant);root=Path(job['root'])
            for name in ('observations.json','tracks.json'):assert sha(overlay/name)==sha(root/case/name)
            for name in ('tracking.json','input_receipt.json','bank.npz','nominal_elements.json','receipt.json','selected.tle','previous.tle','previous_receipt.json'):
                assert sha(SOURCE/case/name)==sha(root/case/name),name
            for p in (SOURCE/'causal_prior'/case).iterdir():
                if p.is_file():assert sha(p)==sha(root/'causal_prior'/case/p.name)
            for name in (case+'.json',case+'_forecast.json'):assert sha(SOURCE/'causal_phase_history'/name)==sha(root/'causal_phase_history'/name)
            expected=floored_noise(proxy,ids,new) if variant=='additions_bin_floor' else proxy
            assert effective(expected,ids)==effective(read(root/case/'radio_noise.json'),ids)
            assert new==set(read(root/case/'research_input_receipt.json')['added_native_observation_ids'])
            prepared=read(root/case/'prepared.json');original=read(SOURCE/case/'prepared.json')
            assert prepared['GLRT_points']==len(rows)
            for key,value in original.items():
                if key not in ('GLRT_points','graph_points','graph_tracks','curved_tracks','measurement_transfer'):assert prepared[key]==value,key
            receipts=[read(p) for p in (root/'read_receipts').glob('*.json')]
            assert len(receipts)>=3 and not any(r['denied_paths'] for r in receipts)
            result=next(r for r in terminal['results'] if r['case']==case and r['variant']==variant)
            assert result['status']=='complete' and result['uid']==1000 and result['total_numerical_seconds']<240
            controls.append(dict(job,status='complete',stratum='development',reused_control=True,seconds=result['total_numerical_seconds'],scientific_inputs_and_effective_noise_exact=True,source_prior_catalogue_budget_equality=True,original_total_cap_seconds=240,worker_concurrency_change_only=[2,4],read_receipt_count=len(receipts),endpoint_values_opened=False,terminal_output_hashes={p:h for p,h in terminal['terminal_output_hashes'].items() if Path(p).is_relative_to(root)}))
    write(HERE/'candidate_control_equality.json',dict(all_passed=True,controls=controls,previous_terminal_seal_sha256=sha(PREVIOUS/'position_final_terminal_seal.json'),previous_protocol_sha256=sha(PREVIOUS/'position_protocol.json'),checks=checks,no_geographic_evaluation=True))
    return controls

def main():
    strata=read(HERE/'baseline_queue/protocol.json')['strata'];cases=strata['held']+strata['development']
    overlays={case:BROADER/'graphs'/case for case in cases}
    # No partial cohort protocol or numerical launch: all handoffs first.
    for case,folder in overlays.items():
        terminal=read(folder/'terminal_seal.json');assert terminal['all_passed'] and not terminal['geographic_inputs']
        for p,h in terminal['files'].items():assert sha(p)==h,p
    controls=reuse_audit(overlays);study=HERE/'coherent_candidates';inputs={};jobs=[];aliases=[];audits=[]
    for case in cases:
        overlay=overlays[case];a=read(overlay/'audit.json');assert a['method']=='exact_R01_coherent_only' and a['no_sparse_union'] and a['no_recovered_donors'] and not a['geographic_inputs']
        for p,h in read(overlay/'terminal_seal.json')['files'].items():inputs[p]=h
        inputs[str(overlay/'terminal_seal.json')]=sha(overlay/'terminal_seal.json')
        rows=read(overlay/'observations.json');original=read(SOURCE/case/'observations.json');tracks=read(overlay/'tracks.json')
        new=set(read(overlay/'new_native_owners.json')['observation_ids'])
        assert new=={o['observation_id'] for o in rows}-{o['observation_id'] for o in original}
        with np.load(SOURCE/case/'bank.npz') as bank:
            bank_audit=input_audit(original,rows,tracks,bank,read(SOURCE/case/'nominal_elements.json'),read(SOURCE/'causal_prior'/case/'receipt.json'),read(SOURCE/case/'tracks.json'))
        stratum='held' if case in strata['held'] else 'development'
        audits.append(dict(case=case,stratum=stratum,new_native=len(new),new_in_graph=a['new_in_graph'],new_curved=a['new_in_curved_graph'],bank_support=bank_audit))
        if not new:
            assert a['baseline_equivalent_inputs']
            for name in ('observations.json','tracks.json'):assert sha(overlay/name)==sha(SOURCE/case/name)
            aliases.extend(dict(case=case,stratum=stratum,variant=v,equivalent_to='baseline',reason='no new coherent native owners; exact original observation/graph bytes') for v in ('additions_bin_floor','additions_proxy'))
            continue
        if case in ('DS24-0011','DS24-0097'):continue
        proxy=estimate(tracks,rows)
        for variant in ('additions_bin_floor','additions_proxy'):
            root=study/'runs'/case/variant;folder=root/case;folder.mkdir(parents=True,exist_ok=False)
            for name in ('tracking.json','input_receipt.json','bank.npz','nominal_elements.json','receipt.json','selected.tle','previous.tle','previous_receipt.json'):shutil.copyfile(SOURCE/case/name,folder/name)
            prior=root/'causal_prior'/case;prior.mkdir(parents=True)
            for p in (SOURCE/'causal_prior'/case).iterdir():
                if p.is_file():shutil.copyfile(p,prior/p.name)
            history=root/'causal_phase_history';history.mkdir()
            for name in (case+'.json',case+'_forecast.json'):shutil.copyfile(SOURCE/'causal_phase_history'/name,history/name)
            for name in ('observations.json','tracks.json'):shutil.copyfile(overlay/name,folder/name)
            noise=floored_noise(proxy,[o['observation_id'] for o in rows],new) if variant=='additions_bin_floor' else copy.deepcopy(proxy)
            noise['source_sha256']={n:sha(folder/n) for n in ('observations.json','tracks.json')};noise['code_sha256']=sha(REPO/'tools/ds23_radio_noise.py');write(folder/'radio_noise.json',noise)
            prepared=read(SOURCE/case/'prepared.json');g=a['graph']
            prepared.update(GLRT_points=len(rows),graph_points=g['graph_points'],graph_tracks=g['graph_tracks'],curved_tracks=g['curved_tracks'],measurement_transfer='Frozen R01 coherent-block additions only plus exact originals')
            write(folder/'prepared.json',prepared)
            write(folder/'research_input_receipt.json',dict(case=case,variant=variant,stratum=stratum,added_native_observation_ids=sorted(new),bank_support_audit=bank_audit,original_rows_exact=True,original_tracking_export_sha256=sha(SOURCE/case/'tracking.json'),no_geographic_inputs=True,fresh_initialization=True,no_sparse_union=True,coherent_handoff_sha256=sha(overlay/'terminal_seal.json')))
            for p in root.rglob('*'):
                if p.is_file():inputs[str(p)]=sha(p)
            jobs.append(dict(case=case,variant=variant,stratum=stratum,root=str(root)))
    original_protocol=read(HERE/'baseline_queue/protocol.json');sources=dict(original_protocol['sources_sha256'])
    for p in [Path(__file__),HERE/'test_prepare_candidates.py',HERE/'candidate_control_equality.json',HERE/'export_endpoints.py',HERE/'test_export_endpoints.py']:
        sources[str(p)]=sha(p)
    for p,h in dict(sources,**inputs).items():assert sha(p)==h,p
    write(study/'protocol.json',dict(original_protocol,jobs=jobs,variants=['additions_bin_floor','additions_proxy'],sources_sha256=sources,inputs_sha256=inputs,primary='additions_bin_floor',secondary='additions_proxy',baseline_queue_only=False,primary_candidate_held_for_coherent_handoff=False,coherent_handoff_sealed=True,candidate='exact frozen R01 coherent application; sparse recoveries used for block nomination only',controls=controls,comparison_aliases=aliases,input_audits=audits,maximum_workers=4,seconds_per_job=240,no_GPS_evaluation_until_all_attempts_terminal=True))
    print(dict(jobs=len(jobs),reused_candidate_controls=len(controls),baseline_equivalent_cases=len(aliases)//2,protocol_sha256=sha(study/'protocol.json')),flush=True)

if __name__=='__main__':main()
