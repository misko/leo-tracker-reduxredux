"""Check whether another penalty's feasible association beats a greedy result.

This is a diagnostic only: never replace the requested sweep's solutions or
select a configuration using position truth. Feasibility gates/pools are fixed.
"""
import json
from satellite_penalty_sweep import OUT, SCANS, ARMS, PENALTIES


def compare(solutions):
    rows = []
    for penalty in PENALTIES:
        scores = {p: r['assigned']-penalty*r['satellites'] for p, r in solutions.items()}
        best = max(scores.values())
        rows.append(dict(evaluated_penalty=penalty, own_score=scores[penalty],
                         best_available_score=best, improvement=best-scores[penalty],
                         best_source_penalties=[p for p, score in scores.items() if score == best]))
    return rows


def main():
    rows = []
    for scan in SCANS:
        for arm in ARMS:
            receipts = {p: json.loads((OUT/f'penalty-{p}'/scan/'associations'/f'{arm}.json').read_text()) for p in PENALTIES}
            assert len({r['source_sha256'] for r in receipts.values()}) == 1
            assert all(r['limits'] == receipts[10]['limits'] for r in receipts.values())
            rows.extend(dict(scan=scan, arm=arm, **r) for r in compare({p: r['final'] for p, r in receipts.items()}))
    report = dict(scope=__doc__, rows=rows, dominated=[r for r in rows if r['improvement'] > 0])
    (OUT/'cross-score-diagnostic.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report['dominated'], indent=2))


if __name__ == '__main__': main()
