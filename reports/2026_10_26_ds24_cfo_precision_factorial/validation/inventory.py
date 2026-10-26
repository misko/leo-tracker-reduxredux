"""Public automatic-status and contract-tail metadata only; no RF arrays."""
import time
STARTED=time.monotonic()
import hashlib
import json
from pathlib import Path
import re
import signal

from leo.storage.fast_scan import FastScanStore

OLD=Path('/srv/bulk/leo/research/ds24-identity-components-r01/audit/exposure_inventory02.json')
USED=Path('/srv/bulk/leo/research/ds24-phase-shape-validation-r01/readiness/panel_protocol.json')


def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return digest(json.dumps(value,sort_keys=True,separators=(',',':')).encode())


def main():
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('10second metadata-only cap')))
    signal.setitimer(signal.ITIMER_REAL,max(.001,10-(time.monotonic()-STARTED)))
    old=json.loads(OLD.read_text());used={r['session_id']for r in json.loads(USED.read_text())['members']}
    store=FastScanStore('/srv/bulk/leo');rows=[]
    recent=store.automatic_page(limit=100)['items']
    oldnames={r['recording_id']for r in old['post_cutoff_direct_job_metadata']}
    unenumerated_recent=[dict(recording_id=x.get('recording_id'),state=x.get('state'),session_id=x.get('session_id'))
        for x in recent if x and x.get('recording_id')not in oldnames and re.search(r'fast8-auto-2026102[4-9]-',x.get('recording_id',''))]
    for saved in old['post_cutoff_direct_job_metadata']:
        job=store.automatic_status(saved['recording_id'])
        q=dict(recording_id=saved['recording_id'],name_time_proxy_utc_ns=saved['recording_name_time_proxy_utc_ns'],
            session_id=saved['session_id'],prior_state=saved['automatic_state'],previous_later8=saved['session_id']in used,
            current_state=job.get('state')if job else None,current_session_id=job.get('session_id')if job else None,
            current_run_id=job.get('run_id')if job else None,current_standard_stages=job.get('standard_stages')if job else None,
            current_public_job_canonical_sha256=canonical(job),contract_metadata=[],full_input_validated_now=False,
            raw_authority_reconstructed_now=False,known_geographic_exposure='previous later-eight published evaluation'if saved['session_id']in used else'unknown beyond exact checked report membership',
            research_parent_ready=False)
        if job and job.get('run_id'):
            p=store.tracking_input_path(job['run_id'])
            if p.is_file():
                with p.open('rb')as f:f.seek(max(0,p.stat().st_size-2048));tail=f.read()
                previous=next((x for x in saved['source_session_matched_contract_metadata']if x['path']==str(p)),None)
                same=bool(previous and previous['trailing_metadata_sha256']==digest(tail)and previous['bytes']==p.stat().st_size)
                q['contract_metadata'].append(dict(path=str(p),bytes=p.stat().st_size,trailing2048_sha256=digest(tail),
                    prior_tail_and_size_unchanged=same,sample_rate_hz=previous['sample_rate_hz']if same else None,
                    qualified=previous['qualified']if same else None,
                    declared_raw_authority_digest=previous['raw_recording_authority_digest']if same else None))
        q['metadata_eligible_remaining']=bool(not q['previous_later8']and q['current_state']=='complete'and q['current_session_id']==q['session_id']and
            any(x['sample_rate_hz']==10000000 and x['qualified']for x in q['contract_metadata']))
        rows.append(q)
    ordered=sorted(rows,key=lambda r:(r['name_time_proxy_utc_ns'],r['recording_id']))
    selected=[r['recording_id']for r in ordered if r['metadata_eligible_remaining']][:4]
    for r in ordered:r['proposed_fixed4_metadata_member']=r['recording_id']in selected
    output=dict(schema='later-block-public-metadata-inventory/v1',selection='first4 chronological saved postcutoff jobs beyond used8 with current complete status and unchanged qualified10MSps metadata; no outcome criterion',
        rows=ordered,proposed_fixed4_recordings=selected,recent_public_page_size=len(recent),additional_recent_page_rows=unenumerated_recent,
        numerical_seconds=time.monotonic()-STARTED,metadata_only=True,IQ_or_RF_arrays=False,positions_or_errors_read=False,
        canonical_capture_times_not_newly_verified=True,untouched_holdout_claimed=False,
        source_bindings={str(p):digest(p.read_bytes())for p in (OLD,USED,Path(__file__))})
    print(json.dumps(output,indent=2),flush=True)


if __name__=='__main__':main()
