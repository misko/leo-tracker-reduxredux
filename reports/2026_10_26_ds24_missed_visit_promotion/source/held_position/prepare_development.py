"""Exact original controls for the separately labeled development stratum."""
from pathlib import Path
import shutil
from position import HERE,SOURCE,OLD,read,write,sha

def main():
    frozen=read(HERE/'baseline_v3/protocol.json')
    equality=read(HERE/'development_control_equality.json');assert equality['all_passed']
    cases=read(OLD.parent/'split.json')['development'];reused={c['case'] for c in equality['controls']}
    study=HERE/'development_baseline';jobs=[];inputs={}
    for case in cases:
        if case in reused:continue
        root=study/'runs'/case/'baseline';folder=root/case;folder.mkdir(parents=True,exist_ok=False)
        for name in ('tracking.json','input_receipt.json','bank.npz','nominal_elements.json','receipt.json','selected.tle','previous.tle','previous_receipt.json','observations.json','tracks.json','radio_noise.json','prepared.json'):
            shutil.copyfile(SOURCE/case/name,folder/name)
        prior=root/'causal_prior'/case;prior.mkdir(parents=True)
        for p in (SOURCE/'causal_prior'/case).iterdir():
            if p.is_file():shutil.copyfile(p,prior/p.name)
        history=root/'causal_phase_history';history.mkdir()
        for name in (case+'.json',case+'_forecast.json'):shutil.copyfile(SOURCE/'causal_phase_history'/name,history/name)
        write(folder/'research_input_receipt.json',dict(case=case,variant='baseline',added_native_observation_ids=[],original_rows_exact=True,original_tracking_export_sha256=sha(SOURCE/case/'tracking.json'),no_geographic_inputs=True,fresh_initialization=True))
        for p in root.rglob('*'):
            if p.is_file():inputs[str(p)]=sha(p)
        jobs.append(dict(case=case,variant='baseline',root=str(root)))
    sources=dict(frozen['sources_sha256']);sources.update({str(p):sha(p) for p in [Path(__file__),HERE/'development_control_equality.json']})
    for p,h in dict(sources,**inputs).items():assert sha(p)==h,p
    write(study/'protocol.json',dict(frozen,jobs=jobs,cases=cases,first_case=jobs[0]['case'],sources_sha256=sources,inputs_sha256=inputs,stratum='development',controls=equality['controls'],control_equality_audit_sha256=sha(HERE/'development_control_equality.json'),primary_candidate_held_for_coherent_handoff=True,baseline_reuse='0011/0097 exact scientific/source/input/prior/candidate/runtime/budget/read-audit equality proven without opening endpoints'))
    print(dict(jobs=len(jobs),reused_controls=sorted(reused),protocol_sha256=sha(study/'protocol.json')),flush=True)

if __name__=='__main__':main()
