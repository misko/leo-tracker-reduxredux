"""Postfit RF-only merge retaining exact authoritative component rows."""
import argparse
from collections import Counter
from pathlib import Path
import sys

# A test or another postfit tool can already own the imported frozen driver.
# Keep that module identity so its functions remain pickleable by Pool.
_existing_driver=sys.modules.get('frozen_generalized_driver')
import complete_coverage as completion
if _existing_driver is not None:
    sys.modules['frozen_generalized_driver']=_existing_driver
    completion.driver=_existing_driver

driver=completion.driver
HERE=Path(__file__).resolve().parent


def merge_rows(components):
    chosen={};provenance={}
    for path,packet in components:
        path=Path(path).resolve();digest=driver.sha(path)
        for row in packet['rows']:
            case=row['case']
            if case in chosen:
                previous=provenance[case]
                folder=Path(previous['results_path']).parent/'cases'/case
                if completion.attempt_evidence(chosen[case],folder)['started']:
                    raise ValueError('A started case appears in a later completion wave: '+case)
            chosen[case]=row
            provenance[case]=dict(results_path=str(path),results_sha256=digest)
    return chosen,provenance


def never_started(chosen,provenance):
    """An empty final queue is valid and needs no inference scheduler."""
    return sorted(case for case,row in chosen.items() if not completion.attempt_evidence(
        row,Path(provenance[case]['results_path']).parent/'cases'/case)['started'])


def validate_packet(packet,roster,expected_protocol):
    if not packet.get('workers_joined'):raise ValueError('Component workers are not joined')
    if packet['protocol_sha256']!=expected_protocol:raise ValueError('Component packet protocol mismatch')
    by_case={r['case']:r for r in packet['rows']}
    if len(by_case)!=len(packet['rows']) or packet['available']!=len(by_case):
        raise ValueError('Component duplicate case or count mismatch')
    records={r['case']:r for r in roster['cases']}
    for case,row in by_case.items():
        if case not in records:raise ValueError('Component case outside frozen roster')
        record=records[case]
        if (row['protocol_sha256']!=expected_protocol or row['input_sha256']!=record['input_sha256']
                or row['identities']!=record['identities']):
            raise ValueError('Component row protocol/input/recording identity mismatch')


def merge(coverage_protocol,component_paths,output):
    coverage_protocol=Path(coverage_protocol).resolve()
    protocol=driver.read(coverage_protocol);policy=protocol['coverage_completion']
    original_path=Path(policy['original_protocol_path'])
    if driver.sha(original_path)!=policy['original_protocol_sha256']:
        raise ValueError('Original scientific protocol changed')
    original=driver.read(original_path);coverage_digest=driver.sha(coverage_protocol)
    paths=[Path(p).resolve() for p in component_paths]
    expected=[HERE/'results.json']+[HERE/name/'results.json' for name in policy['allowed_waves']]
    if not paths or paths!=[p.resolve() for p in expected[:len(paths)]]:
        raise ValueError('Components must be a chronological original/completion prefix')
    if len(paths)>len(expected):raise ValueError('Too many components')
    roster_path=Path(original['evaluation']['roster_path'])
    if driver.sha(roster_path)!=original['evaluation']['roster_sha256']:
        raise ValueError('Original RF roster changed')
    roster=driver.read(roster_path);components=[]
    for index,path in enumerate(paths):
        packet=driver.read(path)
        validate_packet(packet,roster,coverage_digest if index else policy['original_protocol_sha256'])
        if index:
            prior_chosen,prior_provenance=merge_rows(components)
            if {r['case'] for r in packet['rows']}!=set(never_started(prior_chosen,prior_provenance)):
                raise ValueError('Completion component differs from never-started eligibility')
        elif {r['case'] for r in packet['rows']}!={r['case'] for r in roster['cases']}:
            raise ValueError('Original component must retain the entire available roster')
        components.append((path,packet))
    chosen,provenance=merge_rows(components)
    if set(chosen)!={r['case'] for r in roster['cases']}:
        raise ValueError('Combined roster differs from original available population')
    remaining=never_started(chosen,provenance)
    packet=dict(scientific_protocol_sha256=policy['original_protocol_sha256'],
        coverage_protocol_sha256=coverage_digest,coverage_protocol_path=str(coverage_protocol),
        roster_sha256=original['evaluation']['roster_sha256'],
        available=len(chosen),total_source_members=roster['total_source_members'],
        unavailable_source_members=roster['unavailable_source_members'],
        workers_joined=all(p['workers_joined'] for _,p in components),
        component_wall_seconds=[dict(path=str(p),wall_seconds=v['wall_seconds']) for p,v in components],
        components=[dict(path=str(path),sha256=driver.sha(path)) for path,_ in components],
        provenance=provenance,never_started_remaining=sorted(remaining),
        status_counts=dict(Counter(r['status'] for r in chosen.values())),
        variant_status_counts={label:dict(Counter(r['variants'][label]['status'] for r in chosen.values()))
                               for label in ('A','A+B','A+B+C')},
        accepted_pairs={label:sum(r['variants'][label]['accepted'] for r in chosen.values())
                        for label in ('A','A+B','A+B+C')},
        rows=[chosen[case] for case in sorted(chosen)],
        selection='First actually-started row is terminal; only manager-only queue placeholders can be replaced; source rows unmodified',
        geography_read=False)
    output=Path(output)
    if output.exists():raise FileExistsError('Refusing to replace an existing combined RF ledger')
    driver.write(output,packet)
    print(dict(available=packet['available'],never_started=len(remaining),
               accepted_pairs=packet['accepted_pairs'],sha256=driver.sha(output)),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--coverage-protocol',required=True,type=Path)
    ap.add_argument('--component',required=True,action='append',type=Path)
    ap.add_argument('--output',type=Path,default=HERE/'combined_results.json')
    args=ap.parse_args();merge(args.coverage_protocol,args.component,args.output)
