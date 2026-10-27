"""Independent coherent candidate/reuse/effective-weight audit, no fitting."""
from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from audit_implementation import read,write,sha
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
BROADER=HERE.parent/'broader'
WORKER=HERE.parent/'held_position'
PREVIOUS=Path('/srv/bulk/leo/research/ds24-missed-visit-r01/validation/coherent_application')
BIN=10000000/(44*512)


def effective(noise,ids):
    return {oid:noise['per_observation_noise_sigma_hz'][oid] if noise['extra_parameter_BIC_gain']>0 else noise['constant_radio_sigma_hz'] for oid in ids}


def main():
    began=time.monotonic();path=WORKER/'coherent_candidates/protocol.json';p=read(path)
    assert p['coherent_handoff_sealed'] and not p['primary_candidate_held_for_coherent_handoff']
    assert p['maximum_workers']==4 and p['seconds_per_job']==240 and p['BLAS_threads']==1 and p['uid']==1000
    assert p['regional_center']==[37.906,-122.545] and p['box_width_km']==25. and p['start']==[0.,0.]
    assert p['radio_seed_budget']==4 and p['fully_fitted_RF_branches']==3 and p['phase_rounds']==5 and p['steps_per_round']==48
    for file,h in dict(p['sources_sha256'],**p['inputs_sha256']).items():assert sha(file)==h,file
    preflight=read(path.parent/'preflight.json');assert preflight['passed'] and preflight['protocol_sha256']==sha(path)
    for file,h in preflight['read_receipts_sha256'].items():assert sha(file)==h and not read(file)['denied_paths']
    nomination=read(HERE/'nomination_audit.json');eligible={r['case'] for r in nomination['cases'] if r['eligible']}
    caseinfo={r['case']:r for r in nomination['cases']};cases=set(caseinfo)
    assert set(p['cases'])==cases and p['strata']['held']==read(HERE/'protocol_v2.json')['held_cases']
    jobs={(j['case'],j['variant']):j for j in p['jobs']};controls={(j['case'],j['variant']):j for j in p['controls']};aliases={(j['case'],j['variant']):j for j in p['comparison_aliases']}
    assert len(jobs)==len(p['jobs'])==18 and len(controls)==len(p['controls'])==4 and len(aliases)==len(p['comparison_aliases'])==26
    assert not(set(jobs)&set(controls) or set(jobs)&set(aliases) or set(controls)&set(aliases))
    assert set(jobs)|set(controls)|set(aliases)=={(c,v) for c in cases for v in ('additions_bin_floor','additions_proxy')}
    reused=read(WORKER/'candidate_control_equality.json');assert reused['all_passed']
    oldprotocol=read(PREVIOUS/'position_protocol.json');oldterminal=read(PREVIOUS/'position_final_terminal_seal.json')
    assert oldterminal['all_terminal'] and not oldterminal['denied_reads'] and oldterminal['inputs_and_first_attempt_artifacts_unchanged']
    assert reused['previous_terminal_seal_sha256']==sha(PREVIOUS/'position_final_terminal_seal.json')
    expected_budget={'seconds_per_complete_job':240,'BLAS_threads':1,'radio_seed_budget':4,'fully_fitted_RF_branches':3,'phase_rounds':5,'steps_per_round':48,'regional_center':[37.906,-122.545],'box_width_km':25.,'start':[0.,0.]}
    for key,value in expected_budget.items():assert oldprotocol[key]==value
    for file,h in dict(oldprotocol['source_hashes'],**oldprotocol['input_hashes']).items():assert sha(file)==h,file
    outcomes=[]
    for case in p['cases']:
        overlay=BROADER/'graphs'/case;terminal=read(overlay/'terminal_seal.json');audit=read(overlay/'audit.json')
        for file,h in terminal['files'].items():assert sha(file)==h
        rows=read(overlay/'observations.json');original=read(SOURCE/case/'observations.json');ids=[r['observation_id'] for r in rows]
        assert rows[:len(original)]==original and len(ids)==len(set(ids))
        new=set(ids)-{r['observation_id'] for r in original};scales={}
        for variant in ('additions_bin_floor','additions_proxy'):
            key=case,variant
            if key in aliases:
                assert not new and case not in eligible and audit['baseline_equivalent_inputs']
                assert aliases[key]['equivalent_to']=='baseline'
                for name in ('observations.json','tracks.json'):assert sha(overlay/name)==sha(SOURCE/case/name)
                continue
            job=jobs.get(key,controls.get(key));root=Path(job['root']);folder=root/case
            assert sha(overlay/'observations.json')==sha(folder/'observations.json') and sha(overlay/'tracks.json')==sha(folder/'tracks.json')
            assert set(read(folder/'research_input_receipt.json')['added_native_observation_ids'])==new
            for name in ('tracking.json','input_receipt.json','bank.npz','nominal_elements.json','receipt.json','selected.tle','previous.tle','previous_receipt.json'):
                assert sha(folder/name)==sha(SOURCE/case/name)
            for file in (SOURCE/'causal_prior'/case).iterdir():
                if file.is_file():assert sha(root/'causal_prior'/case/file.name)==sha(file)
            for name in (case+'.json',case+'_forecast.json'):assert sha(root/'causal_phase_history'/name)==sha(SOURCE/'causal_phase_history'/name)
            noise=read(folder/'radio_noise.json');scales[variant]=effective(noise,ids)
            assert noise['source_sha256']=={n:sha(folder/n) for n in ('observations.json','tracks.json')}
            if key in controls:
                assert case in ('DS24-0011','DS24-0097') and job['stratum']=='development' and job['seconds']<240
                assert any(j['root']==str(root) and j['case']==case and j['variant']==variant for j in oldprotocol['jobs'])
                for file,h in job['terminal_output_hashes'].items():assert sha(file)==h
                receipts=[read(f) for f in (root/'read_receipts').glob('*.json')]
                assert len(receipts)>=3 and not any(r['denied_paths'] for r in receipts)
        if scales:
            proxy=scales['additions_proxy'];floor=scales['additions_bin_floor']
            assert all(floor[oid]==(max(proxy[oid],BIN) if oid in new else proxy[oid]) for oid in ids)
            assert all(proxy[oid]>0 for oid in ids)
        outcomes.append(dict(case=case,stratum=caseinfo[case]['cohort'],eligible_lane=case in eligible,
            original_GLRT_count=len(original),added_native=len(new),total_GLRT_count=len(rows),
            treatment_source='baseline_equivalent' if not new else 'reused_development_controls' if case in ('DS24-0011','DS24-0097') else 'fresh_regional_jobs',
            proxy_floor_incumbent_effective_scales_exact=True,only_new_owners_receive_floor=True))
    write(HERE/'candidate_protocol_pre_geography_audit.json',dict(all_passed=True,cases=outcomes,
        candidate_protocol_sha256=sha(path),candidate_protocol_path=str(path),
        source_hashes_verified=len(p['sources_sha256']),input_hashes_verified=len(p['inputs_sha256']),
        fresh_jobs=18,reused_development_candidate_controls=4,baseline_equivalent_cases=13,
        all24_case_variant_identities_accounted=True,unmodified_originals_no_sparse_union=True,
        all_effective_noise_floor_and_incumbent_equalities_passed=True,
        reused_source_input_candidate_prior_and_budget_equalities=True,
        noise_estimator_refits=0,new_position_fits=0,IQ_calls=0,geographic_errors_opened=False,
        prior_deterministic_proxy_estimator_source_and_exact_graph_inputs_reused=True,
        evaluation_protocol_sha256=sha(HERE/'protocol_v2.json'),seconds=time.monotonic()-began))
    print(dict(all_passed=True,fresh_jobs=18,reused_controls=4,baseline_equivalent_cases=13,seconds=time.monotonic()-began),flush=True)


if __name__=='__main__':main()
