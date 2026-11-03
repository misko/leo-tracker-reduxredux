"""Inventory metadata versus numerical predictive membership across DS23."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import OUT as COMBINED
from select_ds23_differential_information import OUT
from run_algo01_ds23_sample import read,write


def check(scan,entries):
    return [dict(component=e['component'],declared_points=len(e['observation_ids']),
        numerical_points=len(scan.tracks[e['track_index']]['times']),
        undeclared_numerical_ids=[o for o in scan.tracks[e['track_index']]['observation_ids'] if o not in set(e['observation_ids'])])
        for e in entries if scan.tracks[e['track_index']]['observation_ids']!=e['observation_ids']]


def one(case):
    scan,_,_,_,_,_,entries,_,_=context_signed(case)
    original=check(scan,entries)
    combined_path=COMBINED/case/'result.json'
    # Locate the combined receipt through its documented execution outputs.
    if not combined_path.exists():combined_path=COMBINED/(case+'.json')
    combined=[]
    if combined_path.exists():
        r=read(combined_path)
        if 'policy_model' in r:combined=check(scan,r['policy_model']['entries'])
    return dict(case=case,original_entries=len(entries),original_mismatches=original,
        combined_source=str(combined_path) if combined_path.exists() else None,combined_mismatches=combined)


def main():
    cases=read(COMBINED/'protocol.json')['available_cases']
    with ProcessPoolExecutor(max_workers=12) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,c) for c in cases])]
    result=dict(rows=rows,all_terminal=True,cases=len(rows),
        original_scans_with_mismatches=sum(bool(r['original_mismatches']) for r in rows),
        combined_scans_with_mismatches=sum(bool(r['combined_mismatches']) for r in rows),
        no_data_model_or_position_changed=True)
    write(OUT/'predictive_membership_audit.json',result)
    print({k:v for k,v in result.items() if k!='rows'},flush=True)


if __name__=='__main__':main()
