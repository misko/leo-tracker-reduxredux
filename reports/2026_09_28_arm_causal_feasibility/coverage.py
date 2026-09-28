"""Retrospective causal search-region coverage; NOT a detector or speed benchmark."""
import argparse
import hashlib
import json
from pathlib import Path


def distance(epoch, previous, stride, period):
    delta = (epoch - (previous - stride)) % period
    return min(delta, period - delta)


def covered(candidate, seeds, stride, period, radius, cfo_radius):
    return any(distance(candidate['epoch_sample'], s['epoch_sample'], stride, period) <= radius
               and abs(candidate['acquired_cfo_hz'] - s['acquired_cfo_hz']) <= cfo_radius
               for s in seeds)


def evaluate(rows, refresh, radius, cfo_radius, integer_period=False):
    totals = {}
    for record in rows:
        rate = record['context']['rate_hz']
        counts = totals.setdefault(str(rate), dict(windows=0, full_windows=0,
            local_windows=0, baseline_hits=0, covered_hits=0,
            positive_windows=0, covered_positive_windows=0))
        probes = record['result']['probes']
        for receiver in (0, 1):
            ordered = sorted((p for p in probes if p['receiver_id'] == receiver),
                             key=lambda p: p['probe_index'])
            assert [p['probe_index'] for p in ordered] == list(range(11))
            seeds = []
            previous_ms = 0
            for probe in ordered:
                candidates = probe['candidates']
                stride = (probe['probe_start_ms'] - previous_ms) * rate / 1000
                full = probe['probe_index'] % refresh == 0 or not seeds
                period = round(rate / 750) if integer_period else rate / 750
                retained = candidates if full else [c for c in candidates if
                    covered(c, seeds, stride, period, radius, cfo_radius)]
                hits = sum(c['margin'] >= .025 for c in candidates)
                recovered = sum(c['margin'] >= .025 for c in retained)
                counts['windows'] += 1
                counts['full_windows' if full else 'local_windows'] += 1
                counts['baseline_hits'] += hits
                counts['covered_hits'] += recovered
                counts['positive_windows'] += bool(hits)
                counts['covered_positive_windows'] += bool(recovered)
                # A missed candidate never enters future seeds. Negative retained
                # candidates can seed, as their location would still be measured.
                seeds = retained
                previous_ms = probe['probe_start_ms']
    aggregate = {k: sum(v[k] for v in totals.values()) for k in next(iter(totals.values()))}
    return dict(refresh_windows=refresh, epoch_radius_samples=radius,
                cfo_radius_hz=cfo_radius, by_rate=totals, total=aggregate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--integer-period', action='store_true',
                        help='Sensitivity check using rounded epoch-grid period')
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.baseline.read_text().splitlines()]
    assert len(rows) == 704 and all(r['status'] == 'ok' for r in rows)
    results = [evaluate(rows, refresh, radius, cfo, args.integer_period) for refresh in (2, 4, 8, 16)
               for radius in (2, 8, 32, 128) for cfo in (2000, 8000, 20000)]
    args.output.write_text(json.dumps(dict(
        scope='Optimistic retrospective proposal coverage, not GLRT hit recovery or measured runtime',
        period_model='rounded epoch grid' if args.integer_period else 'physical frame period',
        baseline_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        dwells=len(rows), methods=results), indent=2)+'\n')
    for target in (.9, .8):
        viable = [m for m in results if m['by_rate']['2500000']['covered_hits'] >=
                  target*m['by_rate']['2500000']['baseline_hits']]
        best = min(viable, key=lambda m:(m['by_rate']['2500000']['full_windows'],
                   m['epoch_radius_samples']*m['cfo_radius_hz']))
        print(json.dumps({'target':target, 'best_2p5':best}))


if __name__ == '__main__':
    main()
