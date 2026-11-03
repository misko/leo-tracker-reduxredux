"""Audit cross-frame prediction and keep source-count conclusions conditional."""
import csv,json
from benchmark import ROOT,digest


def main():
    folder=ROOT/'raw-peak-expanded';rp=folder/'replay.json';sources={str(rp):digest(rp)};rows=[];summary={}
    for variant,name in [('alternating','coherent-frame-comparison.json'),('contiguous_refined','coherent-blocked-frame-comparison.json')]:
        path=folder/name;data=json.loads(path.read_text());assert data['source_sha256']==digest(rp);sources[str(path)]=digest(path)
        summary[variant]={}
        for scan in ('A','B'):
            rr=[r for r in data['results'] if r['scan']==scan];comparisons=[r[k] for r in rr for k in ('forward','reverse')]
            summary[variant][scan]=dict(pairs=len(rr),comparisons=len(comparisons),
                one_beats_zero=sum(q['one_test_gain_fraction_vs_zero']>0 for q in comparisons),
                two_beats_zero=sum(q['two_test_gain_fraction_vs_zero']>0 for q in comparisons),
                two_beats_one=sum(q['two_over_one_test_sse']<1 for q in comparisons),
                both_directions_two_beats_one_and_zero=sum(all(r[k]['two_over_one_test_sse']<1 and r[k]['two_test_gain_fraction_vs_zero']>0 and not r[k]['one_frequency_grid_boundary'] for k in ('forward','reverse')) for r in rr))
            for r in rr:
                for direction in ('forward','reverse'):
                    q=r[direction];rows.append(dict(variant=variant,scan=scan,visit=r['probe_key'][0],receiver=r['probe_key'][1],direction=direction,
                        one_test_gain_vs_zero=q['one_test_gain_fraction_vs_zero'],two_test_gain_vs_zero=q['two_test_gain_fraction_vs_zero'],
                        two_over_one_test_sse=q['two_over_one_test_sse'],one_cfo_hz=q['one_cfo_hz'],boundary=q['one_frequency_grid_boundary']))
    with (folder/'coherent-comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (folder/'coherent-summary.json').write_text(json.dumps(dict(summary=summary,sources=sources,
        interpretation='Contiguous-block common-amplitude models do not reliably predict held-out frames. No sampled pair shows a two-source improvement over both one-source and zero prediction in both directions. This does NOT establish single physical sources: frame-varying phase/gain, pilot mismatch or other model inadequacy remain possible. Alternating-frame split has an additional frequency-alias concern. No denominator or assignments changed.'),indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
