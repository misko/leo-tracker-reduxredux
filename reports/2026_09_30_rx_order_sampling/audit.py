"""Audit observation support around already-selected receiver-order endpoints."""
import hashlib
import json
from pathlib import Path


def endpoint(rows, first_ns):
    eligible = sorted((r for r in rows if r['status'] != 'out_of_scope'),
                      key=lambda r: r['prediction_utc_ns'])
    hits = [r for r in eligible if r['status'] == 'unique_hit']
    if first_ns is None:
        assert not hits
        return None
    assert hits and hits[0]['prediction_utc_ns'] == first_ns
    before = [r for r in eligible if r['prediction_utc_ns'] < first_ns]
    previous = before[-1] if before else None
    after = [r for r in eligible if r['prediction_utc_ns'] >= first_ns]
    return {
        'first_hit_ns': first_ns,
        'previous_opportunity_ns': previous['prediction_utc_ns'] if previous else None,
        'previous_status': previous['status'] if previous else None,
        'gap_s': (first_ns - previous['prediction_utc_ns']) / 1e9 if previous else None,
        'post_first_counts': {s: sum(r['status'] == s for r in after)
                              for s in sorted({r['status'] for r in after})},
        'unique_hit_count': len(hits),
        'unique_hit_span_s': (hits[-1]['prediction_utc_ns'] - first_ns) / 1e9,
    }


def main():
    folder = Path(__file__).resolve().parent
    source = folder.parent / '2026_09_28_rx_receiver_order'
    sequences = json.loads((source / 'sequences.json').read_text())['sequences']
    selected = [s for s in sequences if s['uncensored_lag_rx1_minus_rx0_s'] is not None]
    keys = {(s['hypothesis_id'], s['role']) for s in selected}
    rows = {k: [] for k in keys}
    with (source / 'matched-opportunities.jsonl').open() as stream:
        for line in stream:
            r = json.loads(line)
            key = (r['hypothesis_id'], r['role'])
            if key in rows:
                rows[key].append(r)
    events = []
    for s in selected:
        evidence = rows[(s['hypothesis_id'], s['role'])]
        rx = [endpoint([r for r in evidence if r['receiver_id'] == i],
                       s['receivers'][f'rx{i}']['first_hit_utc_ns']) for i in (0, 1)]
        assert all(r and r['previous_status'] == 'no_matching_candidate' for r in rx)
        lag = (rx[1]['first_hit_ns'] - rx[0]['first_hit_ns']) / 1e9
        assert abs(lag - s['uncensored_lag_rx1_minus_rx0_s']) < 1e-9
        events.append({
            'hypothesis_id': s['hypothesis_id'], 'role': s['role'], 'rx': rx,
            'recorded_lag_s': lag,
            'hypothetical_onset_lag_bracket_s': [
                (rx[1]['previous_opportunity_ns'] - rx[0]['first_hit_ns']) / 1e9,
                (rx[1]['first_hit_ns'] - rx[0]['previous_opportunity_ns']) / 1e9],
        })
    out = {
        'interpretation': 'Recorded proxy order only. Brackets assume perfect detection '
                         'and a single onset; neither assumption is established.',
        'total_sequences': len(sequences), 'retained_events': events,
        'sources': {str(p.relative_to(folder.parent.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (source / 'sequences.json', source / 'matched-opportunities.jsonl')},
    }
    (folder / 'results.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
