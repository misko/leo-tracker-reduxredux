"""Saved-artifact reporting only; never invokes a detector, waveform or graph fit."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE/'report'
ALIAS = 1/4.4e-6
FRAME = 10_000_000/750.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def table(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def wrap(x, period=ALIAS):
    return (x+period/2) % period-period/2


def chosen(candidates):
    rows = [c for c in candidates if c['fractional_epoch_status'] == 'complete'
            and all(c[k] is not None for k in ('fractional_margin', 'fractional_epoch_offset_samples',
                'fractional_tracking_cfo_hz', 'fractional_exact_score', 'fractional_control_score'))
            and c['fractional_margin'] >= .025]
    return max(rows, key=lambda c: (c['fractional_margin'], -c['candidate_rank'])) if rows else None


def truths(slot):
    return [s['cfo0']+s['rate']*(slot['time_s']+.01) for s in slot['sources']]


def descriptive_label(value, truth):
    errors = [float(wrap(value-t)) for t in truth]
    near = [i for i, x in enumerate(errors) if abs(x) <= 450.]
    label = ('A', 'B')[near[0]] if len(near) == 1 else ('ambiguous' if near else 'unmatched')
    return label, errors


def candidates(slot):
    rows = []
    truth = truths(slot)
    for rx in slot.get('receivers', []):
        pick = chosen(rx['candidates'])
        for c in rx['candidates']:
            row = dict(sequence=slot['name'], law=slot['law'], visit=slot['visit'],
                       time_s=slot['time_s']+.01, receiver=int(rx['receiver_id']),
                       candidate_rank=c['candidate_rank'], selected=c is pick,
                       fractional_status=c['fractional_epoch_status'],
                       acquired_cfo_hz=c['acquired_cfo_hz'], integer_residual_hz=c['residual_cfo_hz'],
                       fractional_residual_hz=c['fractional_residual_cfo_hz'],
                       final_cfo_hz=c['fractional_tracking_cfo_hz'],
                       margin=c['fractional_margin'],
                       gated=c['fractional_margin'] is not None and c['fractional_margin'] >= .025)
            for j, t in enumerate(truth):
                name = ('A', 'B')[j]
                row['truth_'+name+'_hz'] = t
                row['acquired_minus_'+name+'_circular_hz'] = float(wrap(c['acquired_cfo_hz']-t))
                if c['fractional_tracking_cfo_hz'] is not None:
                    row['final_minus_'+name+'_circular_hz'] = float(wrap(c['fractional_tracking_cfo_hz']-t))
                if c['fractional_epoch_offset_samples'] is not None:
                    ep = c['epoch_sample']+c['fractional_epoch_offset_samples']
                    row['epoch_minus_'+name+'_samples'] = float(wrap(ep-slot['sources'][j]['epoch'], FRAME))
            if c['fractional_tracking_cfo_hz'] is not None:
                row['descriptive_final_label'] = descriptive_label(c['fractional_tracking_cfo_hz'], truth)[0]
            row['descriptive_acquired_label'] = descriptive_label(c['acquired_cfo_hz'], truth)[0]
            rows.append(row)
    return rows


def main():
    OUT.mkdir(exist_ok=False)
    rf = json.loads((HERE/'RF_seal.json').read_text())
    for path, digest in rf['files'].items():
        if sha(path) != digest:
            raise ValueError('RF artifact changed: '+path)
    audit = json.loads((HERE.parent/'audit/measurement_terminal.json').read_text())
    if not audit['all_passed']:
        raise ValueError('terminal audit required')
    slots = [json.loads(p.read_text()) for p in sorted((HERE/'slots').glob('*.json'))]
    peak_rows = [r for s in slots for r in candidates(s)]
    selected = [r for r in peak_rows if r['selected']]
    table(OUT/'all_peaks.csv', peak_rows)
    table(OUT/'selected_candidates.csv', selected)
    by_name_visit = {(s['name'], s['visit']): s for s in slots}
    coverage = []
    for s in slots:
        for rx in (0, 1):
            rows = [r for r in peak_rows if r['sequence'] == s['name'] and r['visit'] == s['visit'] and r['receiver'] == rx]
            for j in range(len(s['sources'])):
                name = ('A', 'B')[j]
                hits = [r for r in rows if r['gated'] and
                        abs(r.get('final_minus_'+name+'_circular_hz', np.inf)) <= 450. and
                        abs(r.get('epoch_minus_'+name+'_samples', np.inf)) <= 3.]
                coverage.append(dict(sequence=s['name'], visit=s['visit'], receiver=rx, source=name,
                    gated_joint_epoch_CFO_hits=len(hits), miss=not hits,
                    selected_joint_hit=any(r['selected'] for r in hits),
                    hits_with_ambiguous_CFO=sum(r.get('descriptive_final_label') == 'ambiguous' for r in hits)))
    table(OUT/'source_coverage.csv', coverage)
    graph_rows = []; track_rows = []; graphs = {}
    protocol = json.loads((HERE/'protocol.json').read_text())
    for spec in protocol['sequences']:
        name = spec['name']+'_'+spec['law']
        graphs[name] = json.loads((HERE/'graphs'/f'{name}.json').read_text())
        for stage, key in (('final', 'actual'), ('acquired', 'acquired_stage')):
            g = graphs[name][key]
            rows_by_id = {r['observation_id']: r for r in g['rows']}
            for rx in (1, 2):
                tracks = [t for t in g['tracks'] if t['receiver'] == rx]
                rx_input = [r for r in g['rows'] if r['receiver'] == rx]
                mixed = 0; counts = Counter(); quality = Counter(); assigned = 0
                for t in tracks:
                    labels = []
                    for identity in t['observation_ids']:
                        r = rows_by_id[identity]
                        s = by_name_visit[(name, r['visit'])]
                        labels.append(descriptive_label(r['measured_cfo_hz'], truths(s))[0])
                    c = Counter(labels); counts.update(c); assigned += len(labels)
                    is_mixed = c['A'] > 0 and c['B'] > 0
                    mixed += is_mixed
                    quality[t['quality_status']] += 1
                    track_rows.append(dict(sequence=name, stage=stage, receiver=rx-1,
                        key=t['key'], points=len(labels), quality_status=t['quality_status'],
                        mixed_descriptive_labels=is_mixed, A=c['A'], B=c['B'],
                        ambiguous=c['ambiguous'], unmatched=c['unmatched'],
                        rms_hz=t.get('residual_rms_hz'),
                        quality_flags=json.dumps(t['diagnostics']['quality_flags'])))
                graph_rows.append(dict(sequence=name, stage=stage, receiver=rx-1,
                    graph_input=len(rx_input), tracks=len(tracks), assigned=assigned,
                    unresolved=len(rx_input)-assigned, mixed_descriptive_tracks=mixed,
                    A=counts['A'], B=counts['B'], ambiguous=counts['ambiguous'], unmatched=counts['unmatched'],
                    no_structure_detected=quality['no_structure_detected'],
                    structure_flagged=quality['structure_flagged'], insufficient_support=quality['insufficient_support']))
    table(OUT/'graph_summary.csv', graph_rows)
    table(OUT/'track_diagnostics.csv', track_rows)
    oracle_rows = []
    for name in graphs:
        oracle = json.loads((HERE/'graphs'/f'{name}_oracle.json').read_text())
        for source, g in oracle.items():
            oracle_rows.append(dict(sequence=name, source=source, input=len(g['rows']),
                assigned=g['assigned'], tracks=len(g['tracks']),
                quality_statuses=[t['quality_status'] for t in g['tracks']]))
    write(OUT/'oracle_controls.json', oracle_rows)
    # Closure stage comparison includes all finite alias-circular errors; acquisition
    # outliers remain visible on symlog rather than being clipped to the final branch.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    closure = [r for r in selected if r['sequence'].startswith('closure_')]
    closure_order = ['sampled_deployed', 'sampled_right', 'continuous']
    for ax, condition in zip(axes, ('single', 'overlap')):
        for row in closure:
            if not row['sequence'].endswith(condition):
                continue
            y = closure_order.index(row['law'])+(row['receiver']-.5)*.16
            ax.plot([row['acquired_minus_A_circular_hz'], row['final_minus_A_circular_hz']], [y, y], color='.7')
            ax.scatter(row['acquired_minus_A_circular_hz'], y, color='#cf7c23', marker='x', s=48)
            ax.scatter(row['final_minus_A_circular_hz'], y, color='#1966ad', s=24)
        ax.set_yticks(range(3), ['Deployed sampled', 'Right-boundary sampled', 'Continuous exact period'])
        ax.invert_yaxis(); ax.axvline(0, color='.6', linewidth=.8)
        ax.set_xscale('symlog', linthresh=1.)
        ax.set_xlabel('Circular CFO error to A (Hz; symlog above 1 Hz)')
        ax.set_title('One source' if condition == 'single' else 'Two coincident-epoch sources')
        ax.grid(alpha=.2)
    fig.legend(handles=[Line2D([], [], marker='x', color='#cf7c23', linestyle='', label='Acquired CFO'),
                       Line2D([], [], marker='o', color='#1966ad', linestyle='', label='Selected final CFO')],
               loc='outside upper center', ncol=2)
    fig.savefig(OUT/'closure_stages.png', dpi=170); plt.close(fig)
    # Receiver trajectories and their original graph polynomial pieces.
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained', sharex=True)
    colors = ('#1966ad', '#d67829')
    for row, base in enumerate(('coincident', 'separated')):
        for column, law in enumerate(('sampled_deployed', 'continuous')):
            ax = axes[row, column]; name = base+'_'+law; g = graphs[name]['actual']
            ts = np.arange(16)+.01
            ax.plot(ts, 100000+200*ts, color='black', linestyle='--', linewidth=1, label='True A')
            ax.plot(ts, 103000-200*ts, color='.5', linestyle=':', linewidth=1.5, label='True B')
            for rx in (1, 2):
                r = [x for x in g['rows'] if x['receiver'] == rx]
                ax.scatter([x['time_s'] for x in r],
                    [100000+float(wrap(x['measured_cfo_hz']-100000)) for x in r],
                    s=28, marker=('o', 'x')[rx-1], color=colors[rx-1], label=f'RX{rx-1} selected')
                for track in [t for t in g['tracks'] if t['receiver'] == rx]:
                    for piece in track['pieces']:
                        t = np.linspace(piece['start_s'], piece['end_s'], 150)
                        v = np.polynomial.legendre.legval((t-piece['reference_time_s'])/piece['time_scale_s'], piece['coefficients_hz'])
                        v = 100000+wrap(v-100000)
                        ax.plot(t, v, color=colors[rx-1], alpha=.7,
                                linestyle='-' if track['quality_status'] == 'no_structure_detected' else '-.')
            ax.set_title(f'{base.capitalize()} epochs · '+('deployed sampled' if law == 'sampled_deployed' else 'continuous'))
            ax.set_ylabel('CFO, shown near A’s alias branch (Hz)'); ax.grid(alpha=.2)
            if row == 1:
                ax.set_xlabel('Synthetic sequence time (s; 1 s cadence)')
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncol=4)
    fig.savefig(OUT/'graph_continuity.png', dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 6), layout='constrained', sharey=True)
    sequences = list(graphs)
    palette = {'A': '#368441', 'B': '#8651aa', 'ambiguous': '#a5a5a5', 'unmatched': '#b83f39'}
    for ax, stage in zip(axes, ('final', 'acquired')):
        for i, name in enumerate(sequences):
            for rx in (0, 1):
                r = next(r for r in graph_rows if (r['sequence'], r['stage'], r['receiver']) == (name, stage, rx))
                y = 2*i+rx; left = 0
                for label, color in palette.items():
                    ax.barh(y, r[label], left=left, color=color, height=.7)
                    left += r[label]
                ax.text(max(16., left)+.3, y, f"{r['tracks']} tracks; {r['mixed_descriptive_tracks']} mixed", va='center', fontsize=8)
        ax.set_title('Actual final CFO graph' if stage == 'final' else 'Same selection, acquired CFO graph')
        ax.set_xlabel('Graph-owned points by descriptive CFO proximity')
        ax.set_xlim(0, 27); ax.set_xticks([0, 4, 8, 12, 16]); ax.grid(axis='x', alpha=.2)
    axes[0].set_yticks(range(8), [f"{n.replace('_sampled_deployed', ' · sampled').replace('_continuous', ' · continuous')} RX{rx}"
        for n in sequences for rx in (0, 1)])
    axes[0].invert_yaxis()
    fig.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c, label=k) for k, c in palette.items()],
               loc='outside upper center', ncol=4)
    fig.savefig(OUT/'graph_labels.png', dpi=170); plt.close(fig)
    sequence_summary = []
    for name in graphs:
        s = [r for r in selected if r['sequence'] == name]
        cov = [r for r in coverage if r['sequence'] == name]
        sequence_summary.append(dict(name=name, selected=len(s), receiver_windows=32,
            all_peak_source_slots=len(cov), source_slots_without_gated_epoch_CFO_hit=sum(r['miss'] for r in cov),
            selected_descriptive_labels=dict(Counter(r['descriptive_final_label'] for r in s)),
            final_graph=[r for r in graph_rows if r['sequence'] == name and r['stage'] == 'final'],
            acquired_graph=[r for r in graph_rows if r['sequence'] == name and r['stage'] == 'acquired']))
    summary = dict(RF_seal_sha256=sha(HERE/'RF_seal.json'), protocol_sha256=sha(HERE/'protocol.json'),
        slots=len(slots), completed_slots=sum(s['status'] == 'complete' for s in slots),
        receiver_windows=sum(len(s.get('receivers', [])) for s in slots),
        exported_peaks=len(peak_rows), selected=len(selected),
        closure_selected=closure, sequences=sequence_summary,
        graph_summary=graph_rows, oracle=oracle_rows,
        execution=json.loads((HERE/'execution.json').read_text()),
        no_identity_or_position_claim=True)
    write(OUT/'summary.json', summary)
    files = [Path(__file__), *[p for p in OUT.iterdir() if p.is_file()]]
    write(OUT/'seal.json', dict(RF_seal_sha256=sha(HERE/'RF_seal.json'),
        files={str(p): sha(p) for p in files}))
    print(json.dumps(dict(slots=len(slots), peaks=len(peak_rows), selected=len(selected),
                         sequence_summary=sequence_summary), indent=2))


if __name__ == '__main__':
    main()
