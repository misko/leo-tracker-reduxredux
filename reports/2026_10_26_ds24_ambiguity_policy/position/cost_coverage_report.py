"""Saved checkpoint/cost/ownership accounting; no model evaluations."""
import csv
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/'cost_coverage'
OLD=Path('/srv/bulk/leo/research/ds24-ambiguity-position-r01/ambiguity')
OWNERSHIP=Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership/DS24-0011/parent.json')
read=lambda path:json.loads(Path(path).read_bytes())
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    for name,digest in read(HERE/'RF_seal.json')['files'].items():
        if sha(name)!=digest:raise ValueError('scientific file changed: '+name)
    OUT.mkdir(exist_ok=False)
    execution=read(HERE/'execution.json');original=read(OWNERSHIP)['coverage']
    meta=read(OLD/'prepared/DS24-0011/metadata.json')
    counts={}
    for norad in meta['pool']:
        support=read(OLD/'DS24-0011/center'/(str(norad)+'_support.json'))
        cuts=sorted(set([-15.,15.]+support['interpolation_breakpoints']))
        counts[str(norad)]=(len(cuts)-1)*16
    progress=[];lost_rows=[]
    for slot in execution['all6_slots']:
        arm,method=slot['arm'],slot['method'];folder=HERE/arm/method
        epochs=[read(path) for path in sorted(folder.glob('epoch*.json'))]
        progress.append(dict(arm=arm,method=method,status=slot['status'],saved_completed_outer_rounds=len(epochs),
            required_outer_rounds=5,completed_round_residual_evaluations=sum(row['fit']['evaluations'] for row in epochs),
            evaluation_count_excludes_interrupted_round=True,last_completed_round_stop=epochs[-1]['fit']['stopped'] if epochs else None,
            last_completed_round_phase_change_s=epochs[-1]['phase_change_s'] if epochs else None,
            final_endpoint_available=(folder/'raw_endpoint.json').exists(),
            equal_per_method_fit_cap_seconds=60,reported_complete_method_seconds=slot.get('seconds'),
            rule_nodes_per_candidate=json.dumps(counts),mixture_nodes_per_uncached_score=sum(counts.values()),
            partial_is_endpoint_or_movement_result=False))
        if not (folder/'gates.json').exists():continue
        gates=read(folder/'gates.json');lost=set(gates['original_accepted_IDs_lost'])
        assigned=set()
        for association in original[arm]['associations']:
            ids=lost&set(association.get('observation_ids',[]))
            if not ids:continue
            if assigned&ids:raise ValueError('original lost-ID owner duplication')
            assigned|=ids
            lost_rows.append(dict(arm=arm,method=method,component=association['component'],norad=association['norad'],
                source_role=association['association_source'],lost_ID_count=len(ids),
                all_lost_IDs_postfit_only=ids<=set(original[arm]['postfit_only_observation_ids']),
                original_likelihood_ID_loss=len(ids&(set(original[arm]['curved_observation_ids'])|set(original[arm]['predictive_observation_ids']))),
                observation_IDs=json.dumps(sorted(ids))))
        if assigned!=lost:raise ValueError('unmapped original accepted-ID loss')
    for name,rows in [('progress.csv',progress),('lost_source_families.csv',lost_rows)]:
        with (OUT/name).open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    files={str(path):sha(path) for path in OUT.iterdir() if path.is_file()}
    for path in [Path(__file__),HERE/'RF_seal.json',OWNERSHIP]:files[str(path)]=sha(path)
    with (OUT/'seal.json').open('x') as stream:json.dump(dict(files=files,new_model_evaluations=0),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(progress_slots=len(progress),lost_source_rows=len(lost_rows),mixture_phase_nodes_per_score=sum(counts.values()))))


if __name__=='__main__':main()
