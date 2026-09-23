"""Render sealed first-training-scan search traces and post-seal truth overlay."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    path = HERE / 'results/results.json'
    result = json.loads(path.read_text())
    reference = result['reference_coordinate']
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), layout='constrained')
    for ax, search in zip(axes, result['searches'], strict=True):
        centre = {'sacramento': (38.5816, -121.4944, 250),
                  'reno': (39.5296, -119.8138, 500)}[search['prior']]
        rows = search['trace']
        points = ax.scatter([r['east_km'] for r in rows], [r['north_km'] for r in rows],
                            c=[r['objective_rmse_hz'] for r in rows], s=16, cmap='viridis_r')
        chosen = search['selected']
        ax.scatter(chosen['east_km'], chosen['north_km'], marker='*', s=220,
                   c='red', edgecolors='black', label='Training-selected position')
        lat, lon = np.deg2rad(centre[:2])
        target_lat, target_lon = np.deg2rad([reference['latitude_deg'], reference['longitude_deg']])
        delta_lon = target_lon - lon
        bearing = np.arctan2(np.sin(delta_lon) * np.cos(target_lat),
                            np.cos(lat) * np.sin(target_lat)
                            - np.sin(lat) * np.cos(target_lat) * np.cos(delta_lon))
        angle = np.arccos(np.clip(np.sin(lat) * np.sin(target_lat)
                                 + np.cos(lat) * np.cos(target_lat) * np.cos(delta_lon), -1, 1))
        ax.scatter(6371.0088 * angle * np.sin(bearing), 6371.0088 * angle * np.cos(bearing),
                   marker='X', s=120, c='white', edgecolors='black', label='Reference (post-seal)')
        ax.add_patch(plt.Circle((0, 0), centre[2], fill=False, color='black', linewidth=.8))
        ax.set(aspect='equal', xlabel='East of prior centre (km)', ylabel='North (km)',
               title=f"{search['prior'].title()} · {chosen['reference_error_km']:.2f} km error")
        ax.legend(fontsize=8)
        fig.colorbar(points, ax=ax, label='Training capped RMS (Hz)')
    fig.suptitle('Blind single-scan TRAIN baseline · tau = 0\nReference shown only after inference')
    fig.savefig(HERE / 'results/search.png', dpi=150)
    plt.close(fig)
    receipt = {'result_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               'renderer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'png_sha256': hashlib.sha256((HERE / 'results/search.png').read_bytes()).hexdigest()}
    (HERE / 'results/render_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
