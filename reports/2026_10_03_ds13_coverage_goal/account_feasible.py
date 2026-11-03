"""Account for every canonical observation under a feasible development result."""
import json
import numpy as np
from benchmark import ROOT,digest


def main():
    output={}
    for scan in 'AB':
        source=ROOT/'development-tracklets'/f'{scan}-feasible.json'
        result=json.loads(source.read_text())
        proposals=json.loads((ROOT/'development-expanded'/f'{scan}-proposals.json').read_text())['proposals']
        a=np.load(ROOT/'frozen'/f'{scan}-observations.npz');groups=a['group']
        assigned={r['row_index'] for r in result['assignments']}
        owned={(int(groups[r['row_index']]),r['catalog_number']) for r in result['assignments']}
        selected_edges={};all_edges={}
        for pi,p in enumerate(proposals):
            for s in p['segments']:
                for row in s['eligible_rows']:
                    all_edges.setdefault(row,set()).add(p['catalog_number'])
                    if result['selected_modes'].get(str(p['catalog_number']))==pi:
                        selected_edges.setdefault(row,set()).add(p['catalog_number'])
        ledger={'assigned_unvalidated':[],'competing_peak_for_already_assigned_satellite':[],
                'other_edge_to_selected_mode':[],'only_unselected_mode_or_satellite':[],'no_in_segment_edge':[]}
        for row in map(int,a['canonical_rows']):
            if row in assigned:key='assigned_unvalidated'
            elif any((int(groups[row]),n) in owned for n in selected_edges.get(row,())):
                key='competing_peak_for_already_assigned_satellite'
            elif row in selected_edges:key='other_edge_to_selected_mode'
            elif row in all_edges:key='only_unselected_mode_or_satellite'
            else:key='no_in_segment_edge'
            ledger[key].append(row)
        assert sum(map(len,ledger.values()))==len(a['canonical_rows'])
        assert len({r for values in ledger.values() for r in values})==len(a['canonical_rows'])
        output[scan]=dict(counts={k:len(v) for k,v in ledger.items()},rows=ledger,source_sha256=digest(source),
                          interpretation='Competing peaks are not proven duplicate signals. They remain in the denominator and do not count as assigned coverage.')
        print(scan,output[scan]['counts'])
    (ROOT/'development-tracklets/accounting.json').write_text(json.dumps(output,indent=2))


if __name__=='__main__':main()
