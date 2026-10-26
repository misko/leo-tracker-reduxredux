"""Saved-output summaries only; this module never calls the detector."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / 'report'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(name, rows):
    with (OUT / name).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    data = json.loads((HERE / 'results.json').read_text())
    protocol = json.loads((HERE / 'protocol.json').read_text())
    assert len(data['slots']) == 16
    assert {(s['scenario'], s['seed']) for s in data['slots']} == {
        (name, seed) for name, _ in protocol['scenarios'] for seed in protocol['seeds']}
    for path, digest in protocol['files'].items():
        assert sha(Path(path)) == digest, path
    receivers, candidates = [], []
    for slot in data['slots']:
        if slot['status'] != 'complete':
            continue
        assert slot['input']['clipping_samples'] == 0
        assert len(slot['receivers']) == 2
        sources = slot['sources']
        reference = sources[0]['cfo_hz'] + .01 * sources[0]['rate_hz_s'] if sources else None
        for receiver in slot['receivers']:
            summary = receiver['summary']
            winner = summary['highest_margin_accepted']
            fractional = [c for c in receiver['candidates']
                          if c['fractional_epoch_status'] == 'complete'
                          and c['fractional_margin'] is not None]
            accepted = [c for c in fractional if c['fractional_margin'] >= .025]
            assert summary['accepted_count'] == len(accepted)
            assert winner == (max(accepted, key=lambda c: c['fractional_margin']) if accepted else None)
            key = dict(scenario=slot['scenario'], seed=slot['seed'], receiver_id=receiver['receiver_id'])
            receivers.append(dict(**key, candidate_count=len(receiver['candidates']),
                fractional_count=summary['fractional_count'], accepted_count=len(accepted),
                highest_margin=max((c['fractional_margin'] for c in fractional), default=None),
                selected_rank=winner['candidate_rank'] if winner else None,
                selected_CFO_hz=winner['fractional_tracking_cfo_hz'] if winner else None,
                strongest_source_midpoint_CFO_hz=reference,
                selected_minus_strongest_midpoint_hz=(winner['fractional_tracking_cfo_hz']-reference)
                    if winner and reference is not None else None,
                selected_epoch_sample=(winner['epoch_sample']+winner['fractional_epoch_offset_samples'])
                    if winner else None))
            for c in receiver['candidates']:
                candidates.append(dict(**key, **c,
                    fractional_gate_pass=(c in accepted),
                    highest_margin_selection=(winner is not None and c['candidate_rank'] == winner['candidate_rank'])))
    write_csv('receivers.csv', receivers)
    write_csv('candidates.csv', candidates)
    scenario_summary = []
    for name, sources in protocol['scenarios']:
        rows = [r for r in receivers if r['scenario'] == name]
        errors = [r['selected_minus_strongest_midpoint_hz'] for r in rows
                  if r['selected_minus_strongest_midpoint_hz'] is not None]
        margins = [r['highest_margin'] for r in rows if r['highest_margin'] is not None]
        scenario_summary.append(dict(scenario=name, complete_receiver_outputs=len(rows),
            outputs_with_acceptance=sum(r['accepted_count'] > 0 for r in rows),
            mean_selected_difference_hz=float(np.mean(errors)) if errors else None,
            minimum_selected_difference_hz=min(errors) if errors else None,
            maximum_selected_difference_hz=max(errors) if errors else None,
            minimum_highest_margin=min(margins) if margins else None,
            maximum_highest_margin=max(margins) if margins else None))
    write_csv('scenarios.csv', scenario_summary)
    labels = ['Isolated\nstrong', 'Isolated\nweak', 'Same epoch\n500 Hz apart',
              'Same epoch\n3,000 Hz apart', 'Separate epoch\n500 Hz apart',
              'Separate epoch\n3,000 Hz apart', 'Chirp\nvs midpoint']
    rows = scenario_summary[1:]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7.4), sharex=True)
    for i, row in enumerate(rows):
        samples = [r for r in receivers if r['scenario'] == row['scenario']]
        offsets = np.linspace(-.12, .12, len(samples))
        axes[0].scatter(i+offsets, [r['selected_minus_strongest_midpoint_hz'] for r in samples],
                        color='#3d62a8', s=35, zorder=3)
        axes[0].annotate(f"{row['mean_selected_difference_hz']:+.2f} Hz", (i, row['mean_selected_difference_hz']),
                         xytext=(0, 10), textcoords='offset points', ha='center', fontsize=9)
        axes[1].scatter(i+offsets, [r['highest_margin'] for r in samples], color='#3d62a8', s=35)
    axes[0].axhline(0, color='black', linewidth=.8)
    axes[0].set_ylabel('Highest-margin CFO minus stronger\nsource midpoint frequency (Hz)')
    axes[0].set_ylim(-510, 110)
    axes[1].axhline(.025, color='#b94444', ls='--', label='Fractional margin gate = 0.025')
    axes[1].set_ylabel('Highest fractional GLRT margin')
    axes[1].set_ylim(0, .95)
    axes[1].set_xticks(range(7), labels)
    axes[1].legend(loc='lower right')
    for ax in axes:
        ax.grid(alpha=.2)
    noise = scenario_summary[0]
    fig.suptitle('Pilot-only detector control: epoch overlap can displace a confident CFO estimate', fontsize=14)
    fig.text(.5, .015,
        'Four outputs per case: two seeds × two receivers. Noise-only: 0/4 accepted. Known template boundary mismatch; no field or position claim.',
        ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .95))
    fig.savefig(OUT/'highest_margin_diagnostics.png', dpi=180)
    fig.savefig(OUT/'highest_margin_diagnostics.pdf')
    plt.close(fig)

    fig, axes = plt.subplots(2, 4, figsize=(15, 8))
    names = ['Noise only'] + labels
    for ax, (name, sources), title in zip(axes.flat, protocol['scenarios'], names):
        reference = sources[0]['cfo_hz'] + .01*sources[0]['rate_hz_s'] if sources else 0.
        rows = [r for r in candidates if r['scenario'] == name and r['fractional_tracking_cfo_hz'] is not None
                and r['fractional_epoch_status'] == 'complete']
        for row in rows:
            index = 2*protocol['seeds'].index(row['seed']) + row['receiver_id']
            x = index + .012*(row['candidate_rank']-3.5)
            y = row['fractional_tracking_cfo_hz']-reference
            ax.scatter(x, y, s=18, color='#3d62a8' if row['fractional_gate_pass'] else '#aaaaaa', alpha=.7)
            if row['highest_margin_selection']:
                ax.scatter(x, y, marker='*', s=105, color='#111111', zorder=4)
        for source in sources:
            ax.axhline(source['cfo_hz']+.01*source['rate_hz_s']-reference, color='#b94444', ls='--', lw=1)
        ax.set_yscale('symlog', linthresh=10)
        ax.set_xticks(range(4), ['A/R1', 'A/R2', 'B/R1', 'B/R2'])
        ax.set_title(title.replace('\n', ' '), fontsize=10)
        ax.grid(alpha=.2)
        ax.set_xlim(-.4, 3.4)
    for ax in axes[:, 0]:
        ax.set_ylabel('CFO − stronger source midpoint (Hz)\nNoise panel: absolute CFO')
    fig.suptitle('All exported fractional candidates, without truth-based selection or alias folding', fontsize=14)
    fig.text(.5, .015, 'Blue = passes margin; gray = fails; black star = highest-margin accepted; red dashed = generated CFO. Duplicates retained.',
             ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .04, 1, .95))
    fig.savefig(OUT/'all_fractional_candidates.png', dpi=180)
    fig.savefig(OUT/'all_fractional_candidates.pdf')
    plt.close(fig)
    summary = dict(protocol_sha256=sha(HERE/'protocol.json'), results_sha256=sha(HERE/'results.json'),
        total_slots=len(data['slots']), complete_slots=sum(s['status']=='complete' for s in data['slots']),
        receiver_outputs=len(receivers), exported_candidate_records=len(candidates),
        seconds=data['elapsed_seconds'], scenarios=scenario_summary,
        known_template_boundary_mismatch=True, population_inference=False,
        source_identification=False, graph_test=False, position_test=False)
    (OUT/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    files = [p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts
             and p.name not in {'seal.json', 'FINDINGS.md'}]
    (OUT/'seal.json').write_text(json.dumps({str(p.relative_to(HERE)):sha(p) for p in sorted(files)}, indent=2)+'\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
