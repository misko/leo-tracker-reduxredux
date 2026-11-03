"""Resume DBG01 where a rescued scan has no original fit-choice archive."""

import copy
from pathlib import Path

import run_ds23_dbg01_iteration_010 as runner
from run_algo01_ds23_sample import read,write,sha

diagnostic=runner.engine.dbg.engine
ORIGINAL_BANK=diagnostic.bank


def filtered_bank(candidates,needed,state):
    population=[r['component'] for r in candidates[0]['seed']['rows']];nodes=[];excluded=[];seen=set()
    for source in candidates:
        candidate=copy.deepcopy(source)
        if [r['component'] for r in candidate['seed']['rows']]!=population:raise ValueError('bank changed original observation order')
        candidate['seed']['state']=copy.deepcopy(state);key=diagnostic.signature(candidate)
        if key in seen:continue
        seen.add(key);labels={r['candidate_index'] for r in candidate['seed']['rows']}
        if needed-labels:excluded.append(dict(signature=key,missing_predictive_candidate_indices=sorted(needed-labels)))
        else:nodes.append(candidate)
    return nodes,excluded,len(seen)


def bank_with_optional_archive():
    archive=diagnostic.SOURCE/diagnostic.CASE/'fit_radio_noise.json'
    if archive.exists():return ORIGINAL_BANK()
    scan,node,keep,_,old=diagnostic.context()
    discoveries=[read(diagnostic.OUT/f'discovery_{i:02d}.json')['node'] for i in range(13)]
    nodes,excluded,count=filtered_bank([node]+discoveries,{e['candidate_index'] for e in diagnostic.entries_for(old)},diagnostic.zero_state(scan))
    write(diagnostic.OUT/'hypothesis_bank.json',dict(nodes=nodes,excluded=excluded,raw_unique_hypotheses=count,
        same_curved_and_predictive_observations=True,current_predictive_labels_fixed=True,
        archived_fit_choice_file_available=False,missing_archived_fit_choice_path=str(archive),
        rescued_scan_fallback='current complete assignment plus13 actual cold same-scan discoveries; no fabricated archival choices',
        all_candidate_radio_and_phase_states_discarded=True,
        discovery_receipt_sha256={f'discovery_{i:02d}.json':sha(diagnostic.OUT/f'discovery_{i:02d}.json') for i in range(13)},
        finite_whole_assignment_pool_not_exhaustive_catalogue_reassociation=True,
        source_sha256=sha(Path(__file__))))
    return dict(stage='bank',eligible=len(nodes),excluded=len(excluded),rescued_scan_archive_unavailable=True)


def configure():
    runner.configure();diagnostic.bank=bank_with_optional_archive


def main():
    runner.engine.configure=configure;runner.engine.protocol=runner.protocol;runner.engine.main()


if __name__=='__main__':main()
