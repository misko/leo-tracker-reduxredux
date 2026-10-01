"""Plot the sealed fixed-point score contrast without new inference."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest, sealed
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    source = HERE/'iteration96-window-diagnostic-v1.json'
    output = HERE/'iteration96-window-figure-v1.json'
    if output.exists(): raise FileExistsError(output)
    data = sealed(source)
    values = np.asarray([r['quad_minus_single_endpoint'] for r in data['rows']])
    fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
    ax.bar(np.arange(4), values, color=['tab:blue' if v >= 0 else 'tab:orange' for v in values])
    ax.axhline(0, color='black', lw=.8)
    for i, value in enumerate(values):
        ax.annotate(f'{value:+.1f}', (i, value), xytext=(0, 5 if value >= 0 else -5),
                    textcoords='offset points', ha='center', va='bottom' if value >= 0 else 'top')
    ax.set_xticks(np.arange(4), ['S1', 'S2 (46 km fit)', 'S3', 'S4'])
    ax.set_ylim(-60, max(values)*1.17)
    ax.set_ylabel('Acquisition score at quad endpoint − single endpoint')
    ax.set_title('DS9-B05: other scans favor the quad location\nZero nuisance coordinates; fixed-point diagnostic')
    ax.grid(axis='y', alpha=.2)
    figure = output.with_suffix('.png'); fig.savefig(figure, dpi=160)
    value = dict(inputs={str(source): digest(source)}, sources={str(Path(__file__).resolve()): digest(__file__)},
                 figure_sha256=digest(figure), total_contrast=float(values.sum()),
                 qualification='Visualization of the sealed diagnostic; contrasts are not calibrated Bayes factors.')
    with output.open('x') as stream: json.dump(value, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')


if __name__ == '__main__': main()
