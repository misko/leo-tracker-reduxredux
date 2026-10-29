"""Classify a stopped annotation only when saved geometry proves insufficiency."""
import argparse
import hashlib
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import identity_consensus


def finalize(folder,terminal):
    if (folder/'result.json').exists():raise ValueError('never replace an existing annotation')
    receipt=read(terminal);protocol=read(folder/'protocol.json')
    if receipt['status']!='timeout' or receipt['track_id']!=protocol['target']['track_id']:
        raise ValueError('matching terminal timeout receipt required')
    seeds=protocol['seed_list'];invalid=[];completed=[];hashes={}
    for seed in seeds:
        p=folder/f'seed-{seed}.json'
        if not p.exists():continue
        r=read(p);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        if r.get('status')=='insufficient_group_support':invalid.append(seed)
        elif 'proposals' in r:completed.append(r)
    maximum=len(seeds)-len(invalid)
    if maximum>=3:raise ValueError('geometry does not prove insufficient partitions; unfinished fits still required')
    annotation=identity_consensus(completed)
    if annotation['status']!='insufficient_partitions':raise ValueError('inconsistent partial annotation')
    result=dict(job=protocol['job'],component=protocol['target']['component'],track_id=protocol['target']['track_id'],
        folds=completed,annotation=annotation,annotation_prototype=True,no_accepted_associations=True,
        result_kind='geometry_limited_annotation_after_timeout',original_execution_completed=False,
        interrupted_execution=receipt,remaining_candidate_fits_not_executed=True,
        geometry_certificate=dict(invalid_seeds=invalid,maximum_usable_partitions=maximum,required_partitions=3,source_sha256=hashes))
    write(folder/'result.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,required=True);p.add_argument('--terminal',type=Path,required=True)
    a=p.parse_args();r=finalize(a.folder,a.terminal);print(r['annotation']['status'],r['geometry_certificate'])
