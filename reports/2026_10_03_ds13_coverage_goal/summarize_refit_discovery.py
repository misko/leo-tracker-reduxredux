"""Fold-zero rediscovery comparison, not a new held-out validation claim."""
import csv,json
from benchmark import ROOT,digest
from summarize_refit_replay import changes


def main():
    namespace=ROOT/'refit-discovery-evaluation';rows=[];sources={}
    for scan in ('A','B'):
        paths=[ROOT/'heldout-decoding/fold-0'/f'{scan}.json',ROOT/'refit-replay/heldout-decoding/fold-0'/f'{scan}.json',namespace/'heldout-decoding/fold-0'/f'{scan}.json',namespace/'training-union/fold-0'/f'{scan}.json']
        original,refit,new,union=[json.loads(p.read_text()) for p in paths]
        assert original['original_test_rows']==refit['original_test_rows']==new['original_test_rows']==union['original_test_rows']
        assert new['source_sha256']==digest(paths[-1]);sources.update({str(p):digest(p) for p in paths})
        for arm in ('fitted-c','zero-c'):
            u=union['arms'][arm]
            for method in ('activity','history','tracklet'):
                a=original['arms'][arm]['methods'][method];b=refit['arms'][arm]['methods'][method];c=new['arms'][arm]['methods'][method]
                rows.append(dict(scan=scan,arm=arm,method=method,denominator=len(new['original_test_rows']),
                    original_count=a['coherent_test_assigned'],fixed_catalog_refit_count=b['coherent_test_assigned'],
                    rediscovery_count=c['coherent_test_assigned'],rediscovery_fraction=c['coherent_test_coverage'],
                    delta_vs_original=c['coherent_test_assigned']-a['coherent_test_assigned'],
                    predictive_gain_vs_clutter=u['heldout_gain_vs_clutter'],predictive_delta_vs_original=u['heldout_change_vs_original'],
                    **changes(a['assignments'],c['assignments'])))
    with (namespace/'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (namespace/'comparison.json').write_text(json.dumps(dict(scope=__doc__,rows=rows,sources=sources,
        warning='Training-only candidates and refit; all three decoders inspect evaluation peaks for assignment/coherence. Development fold zero only. Identity and false-positive gates remain outstanding. No denominator changes.'),indent=2))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
