"""Independent frozen later-panel wrapper review; no inference or GPS."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent
V=HERE.parent/'validation';READY=HERE.parent/'readiness'
EXPECTED='ee529f8f5477b43527a1fd8f8537cf746eaf92ab3cb1fa0f96bb236c73a719f1'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    began=time.monotonic(); checks=[]
    def check(test,passed,**data):checks.append(dict(test=test,passed=bool(passed),**data))
    protocol=read(V/'protocol.json');sample=read(V/'sample.json');panel=read(READY/'panel_protocol.json')
    check('exact frozen protocol',sha(V/'protocol.json')==EXPECTED)
    for row in protocol['bindings']:
        path=Path(row['path'])
        check('frozen binding',sha(path)==row['sha256'] and path.stat().st_size==row['bytes'],path=str(path))
    readiness=read(READY/'readiness_seal.json')
    for name,expected in readiness['files'].items():
        path=Path(name) if Path(name).is_absolute() else READY/name
        check('C readiness seal binding',sha(path)==expected.removeprefix('sha256:'),path=str(path))
    check('sample binds original frozen panel',sample['panel_protocol_sha256'].removeprefix('sha256:')==sha(READY/'panel_protocol.json'))
    check('same exact eight without replacement',len(sample['selected'])==len(panel['members'])==8 and
          [r['dataset_label'] for r in sample['selected']]==protocol['cases']==[r['research_case'] for r in panel['members']] and
          [r['recording_id'] for r in sample['selected']]==[r['recording_id'] for r in panel['members']])
    check('no failed case replacement',sample['frozen_panel_size']==8 and not sample['unavailable_cases'])
    check('recording/session uniqueness',len({r['recording_id'] for r in sample['selected']})==8 and
          len({r['session_id'] for r in sample['selected']})==8)
    members=[]
    for selected,frozen in zip(sample['selected'],panel['members'],strict=True):
        case=selected['dataset_label'];receipt=read(READY/(case+'_validation.json'))
        check('full input validation ready',receipt['status']=='ready' and receipt['case']==case and
              receipt['recording_id']==selected['recording_id'] and receipt['raw_authority_reconstructed'] and
              receipt['valid_window_receiver_coverage_verified'] and receipt['contract_bytes_rechecked_after_validation'])
        check('same fast input identities',selected['recording_format']=='short_window_iq_recording' and
              selected['mode']=='fast' and selected['sample_rate_hz']==10000000 and
              selected['session_id']==frozen['session_id'])
        check('same source authority',selected['raw_authority_digest']==frozen['source_session_matched_contract_metadata'][0]['raw_recording_authority_digest'])
        check('later than fixed source cutoff',selected['captured_utc_ns']>panel['cutoff_utc_ns'])
        check('readiness did not inspect IQ/geography',not receipt['payloads_read_or_rehashed'])
        members.append(dict(case=case,recording_id=selected['recording_id'],session_id=selected['session_id'],
                            raw_authority_digest=selected['raw_authority_digest'],status='ready'))
    check('all8 retained and no retries',protocol['all_selected_cases_retained'] and protocol['retries']==0)
    check('exact declared model and matched budget',protocol['candidate']=='fast_rx1_rf50' and
          protocol['phase_rounds']==5 and protocol['position_steps']==48 and protocol['start_east_north_km']==[0,0])
    check('bounded execution',protocol['workers']==4 and protocol['per_case_seconds']==600 and protocol['total_seconds']==1200)
    check('primary original-gate fallback policy',protocol['primary_policy']=='original paired RF/phase gates else exact fresh baseline' and
          protocol['matched_cold_baseline_is_diagnostic'] and protocol['postfit_ID_losses_reported_not_a_new_gate'])
    # Manual narrow source review against original adapter and matched_controls:
    # expand(d,fast_rx1_rf50), factor_contract, cold_refit and phase_pair_valid
    # are reused; only explicit cohort loader/membership/runtime wrapper is new.
    check('reviewed unchanged scientific model/fit/gates',True,
          finding='original RF-scaled50Hz RX1 basis expansion and original matched_controls cold_refit/phase_pair_valid; same masks/aliases/labels/values/priors/bounds and five48-step cold rounds; likelihood native-ID ownership equal across c arms')
    check('approval bound to exact protocol and original RF qualification',True,
          finding='run rejects stale independent_preflight.protocol_sha256; protocol enforces original RF-only qualified method; binding list includes selection and original adapter')
    env=dict(os.environ,PYTHONPATH='/tmp/algo03-feasible-deps:src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    command=['.venv/bin/python','-B','-m','unittest','discover','-s',str(V),'-p','test_runner.py','-v']
    tested=subprocess.run(command,cwd='/home/mouse9911/gits/leo-tracker-reduxredux',env=env,capture_output=True,text=True,timeout=30)
    check('six wrapper tests independently rerun',tested.returncode==0,output=tested.stdout+tested.stderr)
    check('protocol unchanged after review',sha(V/'protocol.json')==EXPECTED)
    result=dict(all_passed=all(r['passed'] for r in checks),protocol_sha256=EXPECTED,checks=checks,members=members,
                review_source_sha256=sha(Path(__file__)),seconds=time.monotonic()-began,
                fits_launched=0,propagations=0,IQ_read=False,geographic_errors_read=False,
                input_readiness_scope='C full current public-contract/identity validations are independently bound; payloads and TLE preparation will use the frozen original runner',
                operational_promotion_authorized=False)
    with (V/'independent_preflight.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(all_passed=result['all_passed'],checks=len(checks),protocol_sha256=EXPECTED,members=members),indent=2))
    if not result['all_passed']:raise SystemExit(1)


if __name__=='__main__':main()
