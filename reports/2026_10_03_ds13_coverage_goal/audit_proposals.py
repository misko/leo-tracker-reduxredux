"""Optimistic coverage bounds for the current proposals, NOT validated coverage."""
import json
import numpy as np
from scipy.optimize import linear_sum_assignment
from benchmark import ROOT,digest


def maximum_group_pairs(edges):
    rows=sorted(edges)
    catalogs=sorted({n for options in edges.values() for n in options})
    if not rows or not catalogs:return []
    lookup={n:i for i,n in enumerate(catalogs)}
    allowed=np.zeros((len(rows),len(catalogs)))
    for i,row in enumerate(rows):
        for n in edges[row]:allowed[i,lookup[n]]=1
    rr,cc=linear_sum_assignment(-allowed)
    return [(rows[r],catalogs[c]) for r,c in zip(rr,cc) if allowed[r,c]]


def main():
    manifest=json.loads((ROOT/'frozen/manifest.json').read_text())
    summary={'scope':__doc__,'scans':{}}
    for scan in 'AB':
        source=ROOT/'development-discovery'/f'{scan}-proposals.json'
        receipt=json.loads(source.read_text())
        arrays=np.load(ROOT/'frozen'/f'{scan}-observations.npz')
        groups=arrays['group'];canonical=set(map(int,arrays['canonical_rows']))
        edges={};numbers=set()
        for proposal in receipt['proposals']:
            number=proposal['catalog_number'];numbers.add(number)
            for segment in proposal['segments']:
                assert len(segment['rows'])>=10
                assert len(np.unique(groups[segment['rows']]))==len(segment['rows'])
                for row in segment['rows']:
                    assert row in canonical
                    edges.setdefault(row,set()).add(number)
        pairs=[]
        for group in np.unique(groups):
            rows=np.flatnonzero(groups==group)
            pairs.extend(maximum_group_pairs({int(r):edges[int(r)] for r in rows if int(r) in edges}))
        assert len({r for r,n in pairs})==len(pairs)
        assert len({(int(groups[r]),n) for r,n in pairs})==len(pairs)
        item=dict(distinct_peaks=len(canonical),candidate_catalogs=len(numbers),timing_proposals=len(receipt['proposals']),
                  nonexclusive_row_union=len(edges),exclusive_group_upper_bound=len(pairs),
                  upper_bound_fraction=len(pairs)/len(canonical),target=manifest['scans'][scan]['target_minimum_assigned'],
                  no_current_proposal=len(canonical)-len(edges),lost_to_group_competition=len(edges)-len(pairs),
                  rows_with_multiple_candidate_identities=sum(len(x)>1 for x in edges.values()),
                  proposal_sha256=digest(source),runtime_s=receipt['elapsed_s'],
                  caveat='Allows different timing modes for the same satellite in different groups and ignores identity ambiguity. Upper bound for this proposal set only, not an impossibility proof or achieved coverage.')
        summary['scans'][scan]=item;print(scan,json.dumps(item),flush=True)
    (ROOT/'development-discovery/coverage-audit.json').write_text(json.dumps(summary,indent=2))


if __name__=='__main__':main()
