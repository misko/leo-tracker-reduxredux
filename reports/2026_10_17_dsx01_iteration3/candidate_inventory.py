"""Read-only audit of alternatives discarded by the strongest-margin winner.

Candidate counts are not additional recovered observations. This inventory
does not choose another peak or change the frozen DSX01 denominator.
"""
import csv
from collections import Counter, defaultdict
import json
from pathlib import Path

from leo.application.scanner_trajectory import project_scanner_candidates
from leo.cli.shared_fast_position import load_input
from leo.storage.shared_fast_scan import SharedFastScanStore

HERE=Path(__file__).resolve().parent
DATA=HERE.parent/'2026_10_16_dsx01_fast_association_losses'


def main():
    sources=json.loads((DATA/'sources.json').read_text())
    with (DATA/'membership.csv').open() as stream:membership=list(csv.DictReader(stream))
    context=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    store=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2')
    report=[]
    for source in sources:
        sid=source['source_id']
        job,document,_,_=store.plot_evidence(source['job_id'])
        if (job['input_sha256']!=source['tracking_input_sha256'] or
                job['terminal']['sha256']!=source['terminal_sha256']):
            raise ValueError('Frozen source receipts changed')
        projected=project_scanner_candidates(load_input(document))
        groups=defaultdict(list)
        for candidate in projected:groups[candidate.source_group_id].append(candidate)
        frozen={o['observation_id']:o for o in context if o['source_id']==sid}
        if set(groups)!=set(frozen):raise ValueError('Original unique winning groups changed')
        hist=Counter(len(v) for v in groups.values())
        result=dict(source_id=sid,job_id=job['job_id'],input_sha256=job['input_sha256'],
            terminal_sha256=job['terminal']['sha256'],original_observations=len(frozen),
            passed_candidates=len(projected),candidate_count_per_original_group=dict(sorted(hist.items())),
            windows=[])
        for rid in sorted(set(r['region_id'] for r in membership if r['source_id']==sid)):
            ids=[r['observation_id'] for r in membership if r['region_id']==rid]
            missing=[i for i in ids if not frozen[i]['original_associated']]
            result['windows'].append(dict(region_id=rid,observations=len(ids),original_missing=len(missing),
                originally_missing_with_alternatives=sum(len(groups[i])>1 for i in missing),
                alternative_candidate_count=sum(len(groups[i])-1 for i in ids),
                maximum_candidates_per_group=max(len(groups[i]) for i in ids)))
        report.append(result)
        print(json.dumps(dict(source_id=sid,groups=len(groups),passed_candidates=len(projected),
                              count_histogram=dict(sorted(hist.items())))),flush=True)
    (HERE/'candidate-inventory.json').write_text(json.dumps(dict(sources=report,
        qualification='Passed original fractional-margin-gate alternatives only; no peak substitution or model fitting; frozen original winner remains denominator authority.'),indent=2)+'\n')


if __name__=='__main__':main()
