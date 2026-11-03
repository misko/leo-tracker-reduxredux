"""Keep a verified incumbent in every arm when bounded recovery cannot be audited.

This does not rerun or waive the failed recovery. Installed ALGO04/05 envelopes
must already have selected their normal fallback. No new association is used.
"""
import argparse
from common import *
from leo.contracts.fast_graph_position_v4 import validate_terminal,incumbent_proof

def main(case):
    folder=WORK/'cases'/case;terminal=WORK/'baselines'/case/'terminal.json'
    t=read(terminal);validate_terminal(t,input_sha256=t['input_sha256'])
    proof=incumbent_proof(t['incumbent']);baseline=proof['baseline']
    assert not t['candidate'] and not proof.get('selected')
    assert baseline['read_audit']['all_launched_processes_accounted']
    assert not baseline['read_audit']['historical_result_or_GPS_reads']
    source=read(folder/'retry-algo03/terminal.json')
    assert baseline==source['baseline'] and source['read_audit']['verified'] is False
    previous=read(folder/'receipt.json');assert previous['state']=='failed'
    write(folder/'failed-recovery-receipt.json',previous)
    reason='Bounded ALGO03 recovery process audit incomplete; verified incumbent retained without new recovery'
    write(folder/'receipt.json',dict(previous,state='complete',terminal=str(terminal),decision=t['decision'],
        recovery_unavailable=reason,baseline_reconstruction_root=str(folder/'retry-algo03/recovery'),
        source_terminal_sha256=digest(folder/'retry-algo03/terminal.json'),fallback_terminal_sha256=digest(terminal)))
    write(ROOT/'screen'/case/'result.json',dict(case=case,targets=[],recovery_unavailable=reason))
    write(ROOT/'position'/case/'result.json',dict(case=case,trials={},control={},
        decisions={p:dict(status='recovery_unavailable',reason=reason,excluded=[],eligible_proposals=0) for p in POLICIES},
        conditional_recovery=False,production_changed=False,seconds=0))
    print(case,'verified incumbent retained; no recovery audit waived')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);main(p.parse_args().case)
