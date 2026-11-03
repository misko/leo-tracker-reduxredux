"""Audit and tabulate the five-fold training-only activity prediction diagnostic."""
import argparse,csv,json
from benchmark import ROOT,digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--soft',action='store_true');args=p.parse_args()
    folder=ROOT/('soft-activity-prediction' if args.soft else 'activity-prediction');rows=[];sources={}
    for scan in ('A','B'):
        path=folder/f'{scan}.json';r=json.loads(path.read_text());sources[str(path)]=digest(path)
        assert r['support_radius_s']==17
        for source,sha in r['sources'].items():assert digest(source)==sha
        for arm in ('fitted-c','zero-c'):
            rr=[v for v in r['records'] if v['arm']==arm]
            assert sorted(v['fold'] for v in rr)==list(range(5))
            summary=r['summary'][arm];old=summary['existing_decoder_support']['tracklet']
            assert old['inside_training_activity']+old['outside_training_activity']==old['existing_coherent_test_assignments']
            rows.append(dict(scan=scan,arm=arm,global_gain_vs_clutter=summary['global_gain_vs_clutter'],
                activity_gain_vs_clutter=summary['activity_gain_vs_clutter'],improvement=summary['activity_minus_global'],
                folds_improved=sum(v['activity_minus_global']>0 for v in rr),
                existing_tracklet_assignments=old['existing_coherent_test_assignments'],excluded_by_hard_activity_gate=old['outside_training_activity'],
                excluded_fraction=old['outside_training_activity']/old['existing_coherent_test_assignments']))
            if args.soft:
                assert r['global_mixture_weight']==.1
                rows[-1].update({key:summary[key] for key in ('soft_gain_vs_clutter','soft_minus_global','soft_minus_hard','soft_improves_global_folds','soft_improves_hard_folds')})
    with (folder/'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (folder/'summary.json').write_text(json.dumps(dict(rows=rows,sources=sources,
        interpretation='Training-only activity likelihood diagnostic. Soft model preserves nonzero globally available fallback, with fixed 0.1 group-level mixture weight. Hard-gate exclusion counts describe a hypothetical filter, not applied to assignments. Not a coverage increase or identity validation.'),indent=2))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
