"""Finish only the originally enumerated graph hypotheses after a deadline.

The strict first-attempt deadline outcome stays archived. Completed hypothesis
fits are reused only after checking exact node, mask, entries and prior means.
No new identity, start, gate, prior or iteration budget is added.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import copy
import argparse
import numpy as np
import run_algo04_candidate as study
import repair_algo04_empty_audit as audit_repair
from run_algo01_ds23_sample import read,write,sha

CONFIGURE=study.configure
POSITIONS=study.engine.reentry.positions
CONFIGURATIONS=study.engine.reentry.configurations


def proposal_key(additions):
    return tuple((a['component'],a['candidate_index'],a['alias']) for a in additions)


def resume_positions(d,nominations,path):
    checkpoint=path.with_name(path.stem+'_checkpoint.json')
    done=read(checkpoint)['trials'] if checkpoint.exists() else []
    offered=CONFIGURATIONS(nominations);keys=[]
    for offers in offered:
        additions=[dict(component=r['target']['component'],candidate_index=o['candidate_index'],alias=int(o['aliases'][0])) for r,o in offers]
        keys.append(proposal_key(additions))
    assert [proposal_key(t['additions']) for t in done]==keys[:len(done)]
    for t,offers in zip(done,offered,strict=False):
        node=copy.deepcopy(d['node']);keep=d['keep'].copy()
        for row,offer in offers:
            k=row['row_index'];keep[d['base'].slices[k]]=True
            node['seed']['rows'][k].update(candidate_index=offer['candidate_index'],candidate_norad=offer['norad']);node['aliases'][k]=int(offer['aliases'][0])
        assert node==t['node'] and d['entries']==t['entries']
        np.testing.assert_array_equal(keep,t['mask'])
        np.testing.assert_array_equal(d['all_means'][sorted({r['candidate_index'] for r in node['seed']['rows']})],t['means'])
    if done:write(checkpoint.with_name(checkpoint.stem+'_resume_input.json'),dict(trials=done))
    # Each new checkpoint also retains the completed prefix so a second
    # bounded resume cannot accidentally run an earlier hypothesis again.
    original_write=study.engine.reentry.write
    def checkpoint_write(destination,record):
        if destination==checkpoint:record=dict(record,trials=done+record['trials'])
        original_write(destination,record)
    study.engine.reentry.configurations=lambda _:offered[len(done):]
    study.engine.reentry.write=checkpoint_write
    try:result=POSITIONS(d,nominations,path)
    finally:study.engine.reentry.configurations=CONFIGURATIONS;study.engine.reentry.write=original_write
    trials=done+result['trials'];passing=[t for t in trials if t['paired_valid']]
    passing.sort(key=lambda r:(-r['added_curved_points'],tuple(a['component'] for a in r['additions']),r['arms']['c0']['corrected_selection_loss']))
    selected=passing[0] if passing else None
    return dict(result,trials=trials,selected=selected,policy_arms=selected['arms'] if selected else d['arms'],
        resumed_completed_hypotheses=len(done),original_total_hypotheses=len(offered))


def configure(case):
    raw=CONFIGURE(case)
    # Nominations are deterministic frozen inputs from the failed attempt.
    source=raw/'single_curve_reentry'/(case+'_nominations.json')
    if source.exists():study.engine.reentry.nominate=lambda *_:read(source)
    study.engine.reentry.positions=resume_positions
    return raw


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--available',action='store_true');args=parser.parse_args()
    execution=read(study.OUT/'execution.json')
    if args.available:execution=dict(rows=[read(p) for p in study.RAW.glob('*/result.json')])
    else:assert execution['all_terminal']
    cases=[r['case'] for r in execution['rows'] if r['status']=='failed' and r.get('stage')=='graph' and 'TimeoutError' in (r.get('error') or '')]
    attempts=list(study.OUT.glob('checkpoint_resume_protocol_*.json'));number=len(attempts)+1
    if number>3:raise ValueError('at most three bounded resumes; report remaining incomplete cases')
    protocol=study.OUT/f'checkpoint_resume_protocol_{number}.json'
    write(protocol,dict(cases=cases,source_sha256=sha(Path(__file__)),original_driver_sha256=sha(Path(study.__file__)),
        unchanged_original_hypothesis_set_and_per_hypothesis_solver_budgets=True,
        wall_time_exceeds_first_attempt_deadline=True,strict_deadline_outcomes_archived=True,no_GPS_used=True))
    for case in cases:
        folder=study.RAW/case;archive=folder/f'failed_deadline_attempt_{number}';archive.mkdir()
        for name in ['result.json','execution.log']:(folder/name).rename(archive/name)
    study.configure=configure;study.check=audit_repair.checked
    rows=[]
    with ProcessPoolExecutor(max_workers=min(4,max(1,len(cases)))) as pool:
        for f in as_completed([pool.submit(study.worker,c) for c in cases]):
            row=f.result();rows.append(row);print(row,flush=True)
    write(study.OUT/f'checkpoint_resume_execution_{number}.json',dict(rows=rows,all_terminal=True,all_passed=all(r['status']!='failed' for r in rows)))
    results=[read(study.RAW/c/'result.json') for c in study.freeze()['cases'] if (study.RAW/c/'result.json').exists()]
    if len(results)==410:
        write(study.OUT/'execution.json',dict(rows=[{k:v for k,v in r.items() if k in ['case','status','seconds','stage','error']} for r in results],
            all_terminal=True,all_passed=all(r['status']!='failed' for r in results)))


if __name__=='__main__':main()
