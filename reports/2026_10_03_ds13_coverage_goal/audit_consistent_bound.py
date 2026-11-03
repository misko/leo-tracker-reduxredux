"""Independent primal checks and conditional coverage-ceiling table."""
import csv,json
import numpy as np
from benchmark import ROOT,digest


def validate(records,proposals,groups,canonical):
    edges=[{int(r) for s in p['segments'] for r in s['eligible_rows']} for p in proposals]
    if len(records)!=len({r['row_index'] for r in records}):raise ValueError('Peak reused')
    if len(records)!=len({(int(groups[r['row_index']]),r['catalog_number']) for r in records}):raise ValueError('Satellite reused in probe')
    modes={}
    for r in records:
        row=r['row_index'];pi=r['proposal'];n=r['catalog_number']
        if row not in canonical or row not in edges[pi] or proposals[pi]['catalog_number']!=n:raise ValueError('Invalid edge')
        if n in modes and modes[n]!=pi:raise ValueError('Satellite timing changed')
        modes[n]=pi


def main():
    folder=ROOT/'consistent-coverage-bound';rows=[];sources={}
    for scan in ('A','B'):
        path=folder/f'{scan}.json';result=json.loads(path.read_text());sources[str(path)]=digest(path)
        paths=[ROOT/'development-expanded'/f'{scan}-proposals.json',ROOT/'coarse-fallback'/f'{scan}.json',ROOT/'extended-coarse-fallback'/f'{scan}.json']
        for p in paths:assert digest(p)==result['sources'][str(p)]
        data=[json.loads(p.read_text()) for p in paths];proposals=data[0]['proposals']+data[1]['new_proposals']+data[2]['new_proposals']
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as a:groups=a['group'].copy();canonical=set(a['canonical_rows'].tolist())
        validate(result['assignments'],proposals,groups,canonical)
        assert len(result['assignments'])==result['incumbent_count']
        assert result['upper_bound']>=result['incumbent_count']-1e-5
        rows.append(dict(scan=scan,denominator=len(canonical),target_count=result['target_count'],
            incumbent_count=result['incumbent_count'],solver_upper_bound=result['upper_bound'],
            upper_bound_fraction=result['upper_bound']/len(canonical),
            target_minus_upper_bound=result['target_count']-result['upper_bound'],solver_declared_optimal=result['optimal'],
            mode_inconsistent_optimistic_count=result['optimistic_mode_inconsistent_count']))
    with (folder/'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (folder/'audit.json').write_text(json.dumps(dict(rows=rows,sources=sources,primal_validation='passed',
        interpretation='90% is excluded for this fixed-calibration discrete proposal bank even before priors, identity and final coherence gates. This does not exclude continuous timing/refitting, different calibration, or new physically supported hypotheses. Solver dual bounds are numerical certificates, not interval-arithmetic proofs.'),indent=2))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
