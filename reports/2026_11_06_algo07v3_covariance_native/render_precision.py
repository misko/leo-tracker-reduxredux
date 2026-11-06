"""Render exact loop-state observations from one captured difficult likelihood."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    source = args.profile/'result.json'
    data = json.loads(source.read_bytes())
    assert data['exact'] and data['unchanged_inputs']
    assert all(hashlib.sha256(Path(q).read_bytes()).hexdigest() == digest
               for q, digest in data['bindings'].items())
    shutil.copyfile(source, root/'precision-profile.json')
    rows = data['rows']
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    axes[0].semilogy([r['index'] for r in rows], [r['change'] for r in rows])
    axes[0].axhline(1e-5, color='tab:red', linestyle='--', label='Stopping threshold')
    axes[0].set(xlabel='Precision iteration', ylabel='Maximum absolute log change',
                title=f"{data['iterations']} iterations · {data['repeated_states']} exact repeats")
    axes[0].legend()
    noise = np.abs(np.asarray([r['noise_log_change'] for r in rows]))
    for group in np.argsort(noise[-1])[-3:][::-1]:
        axes[1].semilogy([r['index'] for r in rows],
                         np.maximum(noise[:, group], np.finfo(float).tiny),
                         label=f'Noise group {group}')
    if rows[0]['prior_log_change']:
        axes[1].semilogy([r['index'] for r in rows],
                        [max(abs(v) for v in r['prior_log_change']) for r in rows],
                        label='Maximum learned-prior update')
    axes[1].set(xlabel='Precision iteration', ylabel='Maximum absolute log change',
                title='Groups with the largest remaining noise updates')
    axes[1].legend()
    fig.savefig(root/'precision-trajectory.png', dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
