"""Resume sealed held-identity evidence through matched shared-family trials."""
import argparse
import hashlib
import signal
import time
from pathlib import Path
from types import SimpleNamespace
from debug_fast_graph_unassociated import read, write
from run_phase0265 import ROOT, check_domains
from phase_reference_checks import phase_refresh


def run(source,out):
    from annotate_predictive_only import context
    import include_predictive_annotations as inclusion
    import audit_shared_predictive_inclusion as audit
    began=time.monotonic(); inventory=Path(read(source/'protocol.json')['inventory']); inv=read(inventory); d=context(inv)
    annotation=source/'reference30/annotation'
    if read(annotation/'result.json')['annotation']['status']!='conditionally_supported_identity':
        raise ValueError('passed matched annotation required')
    protocol=dict(annotation=str(annotation),annotation_only_source=str(source),
        annotation_hash=hashlib.sha256((annotation/'result.json').read_bytes()).hexdigest(),
        reference_limits_s=[15,30],same_identity_alias_prior_mask_budget=True,
        GPS_used=False,new_RF=False,new_TLE=False,failed_previous_route=str(source/'failure.json'))
    if not (out/'protocol.json').exists():write(out/'protocol.json',protocol)
    original_make, original_refresh=inclusion.make_event_problem,inclusion.phase_refresh; current={}
    def capture_problem(*a,**k):
        p=original_make(*a,**k); current['p']=p; return p
    inclusion.make_event_problem=capture_problem
    try:
        for limit in (15,30):
            def refresh(phases,reference,limit=limit):
                phase,check=phase_refresh(phases,reference,limit_s=limit)
                p=current['p']; check['next_reference_domain']=check_domains(p,phase,p.linear_entries)
                return phase,check
            inclusion.phase_refresh=refresh
            folder=out/f'reference{limit}'/'inclusion'
            args=SimpleNamespace(output=folder,inventory=inventory,validation=[annotation],
                native_branches=None,native_from_validation=False,predictive_member=True,
                noise_policy='original',position_fit='regional_unconstrained',
                orphan_phase_refresh=False,orphan_orbit_prior=False,target_orbit_prior=False,
                shared_satellite_refresh=False,conditional_satellite_refresh=False,joint_only=False)
            if not (folder/'target_0.json').exists():inclusion.run(args)
            metadata=dict(reference_limit_s=limit,
                same_saved_identity_for_both_reference_limits=True,reference_update_bank_checked=True)
            if not (folder/'reference_experiment.json').exists():write(folder/'reference_experiment.json',metadata)
            old_audit_refresh=audit.phase_refresh
            audit.phase_refresh=lambda actual,reference:phase_refresh(actual,reference,limit_s=limit)
            try:
                if not (folder/'exact_owner_replay.json').exists():audit.run(SimpleNamespace(trial=folder,study=ROOT,output=folder/'exact_owner_replay.json'))
            finally: audit.phase_refresh=old_audit_refresh
    finally: inclusion.make_event_problem,inclusion.phase_refresh=original_make,original_refresh
    paths=list(out.glob('reference*/inclusion/*.json'))+[annotation/'result.json',annotation/'protocol.json',Path(__file__)]
    write(out/'inference_seal.json',dict(GPS_used=False,artifacts_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))
    write(out/'terminal.json',dict(completed=True,inclusion_attempted=True,seconds=time.monotonic()-began))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--resume',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=a.resume)
    def timeout(*unused):raise TimeoutError('590s bounded shared inclusion')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(590)
    try:run(a.source,a.output)
    except Exception as exc:
        write(a.output/('resume_failure.json' if a.resume else 'failure.json'),dict(type=type(exc).__name__,message=str(exc)));raise
