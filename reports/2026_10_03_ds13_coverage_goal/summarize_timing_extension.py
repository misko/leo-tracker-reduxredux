"""Compare fixed-calibration timing retrieval before/after ephemeris-safe extension."""
import csv,json
import numpy as np
from benchmark import ROOT,digest
from feasible_tracklets import compile_proposals,evaluate_mode


def main():
    rows=[];details={};sources={}
    for scan in ('A','B'):
        original=ROOT/'coarse-fallback'/f'{scan}.json';extended=ROOT/'extended-coarse-fallback'/f'{scan}.json'
        before=json.loads(original.read_text());after=json.loads(extended.read_text())
        assert after['source_sha256'][str(original)]==digest(original)
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as a:
            groups=a['group'].copy();times=a['times_s'].copy();canonical=set(a['canonical_rows'].tolist())
        records=after['selection']['assignments']
        assert len(records)==len({r['row_index'] for r in records})
        assert len(records)==len({(int(groups[r['row_index']]),r['catalog_number']) for r in records})
        assert all(r['row_index'] in canonical and abs(r['residual_native_hz'])<=600 for r in records)
        modes=compile_proposals(after['new_proposals'],groups,.8/(13 if scan=='A' else 15));unused=np.zeros(len(groups),bool)
        ranked=sorted([evaluate_mode(m,unused,groups,times) for m in modes],key=lambda x:x['score'],reverse=True)
        details[scan]=[dict(catalog_number=m['catalog_number'],offset_s=after['new_proposals'][m['proposal']]['offset_s'],
            score=m['score'],standalone_coherent_groups=len(m['assignments'])) for m in ranked[:10]]
        rows.append(dict(scan=scan,denominator=len(canonical),new_extended_modes=len(modes),new_catalogs=len(after['summary']['new_catalogs']),
            optimistic_before=before['summary']['optimistic_exclusive_bound'],optimistic_after=after['summary']['optimistic_exclusive_bound'],
            optimistic_after_fraction=after['summary']['optimistic_exclusive_fraction'],
            selected_before=before['summary']['selected_assignments'],selected_after=len(records),selected_after_fraction=len(records)/len(canonical),
            selected_extended_modes=after['summary']['selected_extended_modes'],positive_standalone_extended_modes=int(sum(m['score']>0 for m in ranked)),
            elapsed_seconds=after['summary']['total_seconds']))
        sources.update({str(p):digest(p) for p in (original,extended)})
    folder=ROOT/'extended-coarse-fallback'
    with (folder/'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (folder/'summary.json').write_text(json.dumps(dict(rows=rows,top_standalone_extended_modes=details,sources=sources,
        warning='Development fixed-calibration coarse retrieval, not exhaustive continuous search. Optimistic bound permits different timing modes per probe and ignores priors/identity. Selected counts are not held-out or identity-certified coverage. Original priors and denominator unchanged.'),indent=2))
    print(json.dumps(dict(rows=rows,top_standalone_extended_modes=details),indent=2))


if __name__=='__main__':main()
