"""Compare identical complete scan cohorts after bounded continuation."""
from itertools import product
import json
from statistics import median
from pathlib import Path
from continue_fits import OUT, REPORT
import factorial as study

FIELDS=('refinement','model','cone','arm')
EXPECTED=set(product(('original','refined'),('T1AT','V16'),('off','on'),('fitted-c','zero-c')))


def summarize(rows):
    scans={}
    for r in rows:
        key=tuple(r[k] for k in FIELDS)
        if key not in EXPECTED:raise ValueError('Unknown configuration')
        cases=scans.setdefault(r['scan'],{})
        if key in cases:raise ValueError('Duplicate configuration')
        cases[key]=r
    complete=sorted(s for s,c in scans.items() if set(c)==EXPECTED)
    common=sorted(s for s in complete if all(r['converged'] for r in scans[s].values()))
    stats=[]
    for key in sorted(EXPECTED):
        group=[scans[s][key] for s in complete]
        checked=[scans[s][key] for s in common]
        stats.append(dict(zip(FIELDS,key),n=len(group),
            median_saved_error_m=median(r['distance_m'] for r in group) if group else None,
            unconverged=sum(not r['converged'] for r in group),
            boundary=sum(r['boundary'] for r in group),
            converged_within_1km=sum(r['converged'] and r['distance_m']<=1000 for r in group),
            common_converged_n=len(checked),
            common_converged_median_m=median(r['distance_m'] for r in checked) if checked else None))
    return dict(complete_scans=complete,common_converged_scans=common,configurations=stats)


def main():
    from build_report import table
    rows=[];receipts=[]
    for path in sorted(OUT.glob('*/*/*/*/*.json')):
        r=json.loads(path.read_text());source=Path(r['source'])
        assert study.stage.sha(source)==r['continuation']['source_sha256']
        assert study.stage.sha(source.parent/'input.npz')==r['input_sha256']
        rows.append(r);receipts.append(dict(path=str(path),sha256=study.stage.sha(path)))
    result=summarize(rows);result['sources']=receipts
    def fmt(value):return '—' if value is None else f'{value:.1f}'
    body=['# Position scorecard after optimizer continuation',
        'This comparison uses only scans with all 16 continuation configurations saved. '
        'Every configuration therefore has the same scan denominator. The original fixed-budget '
        'results remain unchanged. Continuation changes optimization effort, not observations, '
        'satellite sets, likelihoods, priors, or the 4 km constraint.',
        f"Complete scans ({len(result['complete_scans'])}/16): "+', '.join(result['complete_scans'])+'.',
        'Saved-error medians retain boundary and unconverged results; they describe the saved '
        'outputs, not a verified ranking of minima. The convergence-qualified success count uses '
        'the full complete-scan denominator and does not credit an unconverged low-error result. '
        'Boundary counts are reported independently of convergence.',
        table(['Measurements','Model','Cone','RF','Scans','Saved median m','Unconverged',
               'Boundary','Converged within 1 km','Common converged median m'],
              [[r['refinement'],r['model'],r['cone'],r['arm'],r['n'],
                fmt(r['median_saved_error_m']),r['unconverged'],r['boundary'],
                f"{r['converged_within_1km']}/{r['n']}",fmt(r['common_converged_median_m'])]
               for r in result['configurations']]),
        f"The final column uses the same {len(result['common_converged_scans'])} scans for every row, "
        'requiring convergence in all 16 configurations: '+', '.join(result['common_converged_scans'])+'. '
        'This removes numerical failures but selects an easier subset, so it cannot replace the full-cohort results. '
        'Boundary solutions remain constrained rather than global certificates.',
        'All fits use the full associated data. These are descriptive development results, not '
        'held-out localization validation. No per-scan best configuration is selected using known '
        'position. Sample-rate groups are different captures, not randomized treatments. The '
        'c = 0 arm disables the final RF coefficient while preserving the fitted-c upstream receiver baseline.',
        '[Per-case continuation results](report.md) · [Fixed-budget comparison](../report.md). '
        'Reproduce with `continuation_scorecard.py` in the scientific Python environment. '
        'The companion JSON contains exact values and source hashes.']
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/'scorecard.json').write_text(json.dumps(result,indent=2))
    (REPORT/'scorecard.md').write_text('\n\n'.join(body)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='sources'}))


if __name__=='__main__':main()
