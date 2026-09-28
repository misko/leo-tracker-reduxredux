"""Render measured tables from the independently validated summary."""
import argparse
import json
from pathlib import Path

ORDER = ['original', 'optimized', 'candidates6', 'candidates4', 'windows6',
         'windows4', 'windows3', 'windows6_candidates2', 'windows4_candidates2', 'progressive4']
LABELS = {'original': 'Original', 'optimized': 'Exact optimized',
          'candidates6': '11 windows × 6 candidates', 'candidates4': '11 windows × 4 candidates',
          'windows6': '6 windows × 8 candidates', 'windows4': '4 windows × 8 candidates',
          'windows3': '3 windows × 8 candidates', 'windows6_candidates2': '6 windows × 2 candidates',
          'windows4_candidates2': '4 windows × 2 candidates', 'progressive4': 'Progressive 4-window start'}


def recovery(science, name):
    value = science['recovery'][name]
    fraction = value['fraction']
    return f"{value['matched']}/{value['denominator']} ({100*fraction:.1f}%)" if fraction is not None else 'N/A'


def render(summary):
    methods = summary['methods']
    lines = ['# Measured GLRT search results', '',
             'Generated from `summary.json`. CPU and wall times are mean per-visit medians across two repeats. '
             'Science counts each visit once. Recovery is relative to the original detector, not physical truth.', '',
             '## Priority: 2.5 MS/s', '',
             '| Method | CPU ms/dwell | Wall ms/dwell | CPU speedup | Confirmations recovered | Positive hypotheses recovered |',
             '|---|---:|---:|---:|---:|---:|']
    for name in ORDER:
        entry = methods[name]['by_rate']['2500000']
        cost = entry['cost']
        lines.append(f"| {LABELS[name]} | {cost['mean_visit_median_cpu_ms']:.1f} | "
            f"{cost['mean_visit_median_wall_ms']:.1f} | {entry['cpu_speedup_vs_fresh_original']:.2f}× | "
            f"{recovery(entry['science'], 'confirmed_receiver_visit_matched_identity')} | "
            f"{recovery(entry['science'], 'positive_candidate_identity')} |")
    lines += ['', '## All supported sample rates', '',
              'Cells show CPU milliseconds per dwell / matched-confirmation recovery. '
              'Higher-rate results each contain only four visits.', '',
              '| Method | 2.5 MS/s | 5 MS/s | 7.5 MS/s | 10 MS/s |',
              '|---|---:|---:|---:|---:|']
    for name in ORDER:
        cells = []
        for rate in ('2500000', '5000000', '7500000', '10000000'):
            entry = methods[name]['by_rate'][rate]
            cells.append(f"{entry['cost']['mean_visit_median_cpu_ms']:.1f} / "
                         + recovery(entry['science'], 'confirmed_receiver_visit_matched_identity'))
        lines.append('| ' + LABELS[name] + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', '## Fastest tested methods passing each development gate', '',
              'This is selection on an exposed development cohort, not an independently validated deployment choice.', '',
              '| Rate MS/s | Required confirmation recovery | Fastest passing method | CPU ms | CPU speedup |',
              '|---:|---:|---|---:|---:|']
    for rate in ('2500000', '5000000', '7500000', '10000000'):
        for threshold in (0.9, 0.8):
            eligible = [(n, m['by_rate'][rate]) for n, m in methods.items()
                if (m['by_rate'][rate]['science']['recovery']['confirmed_receiver_visit_matched_identity']['fraction'] or 0) >= threshold]
            if not eligible:
                lines.append(f'| {int(rate)/1e6:g} | {100*threshold:.0f}% | No measurable passing method | — | — |')
                continue
            name, entry = min(eligible, key=lambda pair: pair[1]['cost']['mean_visit_median_cpu_ms'])
            lines.append(f"| {int(rate)/1e6:g} | {100*threshold:.0f}% | {LABELS[name]} | "
                         f"{entry['cost']['mean_visit_median_cpu_ms']:.1f} | {entry['cpu_speedup_vs_fresh_original']:.2f}× |")
    lines += ['', '## Mixed-rate cohort', '',
              'The average weights the actual 16/4/4/4 visit mix, not a deployment rate distribution.', '',
              '| Method | CPU ms | Wall ms | CPU speedup | Confirmations recovered | Hypotheses recovered | Exact full outputs |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for name in ORDER:
        entry = methods[name]
        science = entry['science']
        exact = science['science_equivalence']
        lines.append(f"| {LABELS[name]} | {entry['cost']['mean_visit_median_cpu_ms']:.1f} | "
            f"{entry['cost']['mean_visit_median_wall_ms']:.1f} | {entry['cpu_speedup_vs_fresh_original']:.2f}× | "
            f"{recovery(science, 'confirmed_receiver_visit_matched_identity')} | "
            f"{recovery(science, 'positive_candidate_identity')} | "
            f"{exact['exact_full_output_equal']}/{exact['successful_row_pairs']} |")
    if summary['run']['receipt'].get('composite'):
        lines += ['', 'This receipt is explicitly composite; consult its predecessor hashes and restart '
                  'provenance. In the reported experiment, only the final 10 MS/s timing repeat spans '
                  'a process restart; all repeat-zero science and both lower-rate repeats precede it.']
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('summary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x') as output:
        output.write(render(json.loads(args.summary.read_text())))
