"""Display comparison receipts for real and controlled publication conditions."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('normal', 'complete', 'partial', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(getattr(args, key).read_text()) for key in ('normal', 'complete', 'partial')]
    labels = ['Original wall clock', 'Controlled: full grid', 'Controlled: stop at 17']
    reference, candidate = [], []
    for row in rows:
        if row['grid_differences']:
            diff, = row['grid_differences']
            assert diff['kind'] == 'incomplete_grid'
            reference.append(diff['reference_evaluated'])
            candidate.append(diff['candidate_evaluated'])
        else:
            assert row['publication_exact']
            reference.append(row['shared_grid_points'])
            candidate.append(row['shared_grid_points'])
    fig, ax = plt.subplots(figsize=(10, 4.8), layout='constrained')
    ax.barh([i - .17 for i in range(3)], reference, height=.3, label='ALGO07 reference')
    ax.barh([i + .17 for i in range(3)], candidate, height=.3, label='Optimized ALGO07*')
    for i, row in enumerate(rows):
        for y, value in [(i - .17, reference[i]), (i + .17, candidate[i])]:
            ax.text(value + 2, y, str(value), va='center', fontsize=10)
        ax.text(198, i, f"{sum(row['png_bytes_equal'].values())}/8 identical PNGs",
                va='center', fontsize=10)
    ax.set(yticks=range(3), yticklabels=labels, xlim=(0, 267),
           xlabel='Paired diagnostic locations evaluated (both calibration arms)')
    ax.invert_yaxis()
    ax.axvline(179, color='black', linestyle='--', linewidth=.8)
    ax.grid(axis='x', alpha=.15)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.17), ncol=2)
    errors = rows[0]['arms']
    ax.set_title('DS26-0002: artifact comparisons under three test conditions\n'
                 f"All retain c=0 error {errors['c0']['evaluation_error_m']:.1f} m; "
                 f"fitted-c {errors['fitted_c']['evaluation_error_m']:.1f} m")
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
