"""Describe bound quality fields without tuning geographic performance."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    source = HERE/'quality-overlay-v4/overlay.json'
    assert digest(source) == source.with_suffix('.sha256').read_text().strip()
    data = json.loads(source.read_text())
    for path,value in data['sources'].items(): assert digest(path) == value
    rows=[]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    for row in data['results']:
        assert row['status'] == 'bound'
        assert digest(row['observation_path']) == row['observation_sha256']
        points = list({p['candidate_id']:p for t in row['tracks'] for p in t['points']}.values())
        result = dict(unit=row['unit'], tracks=row['matched_tracks'], samples=row['matched_samples'], unique_candidates=len(points),
                      extra_projected_tracks=row['extra_projected_tracks'], fields={})
        for ax,field in zip(axes, ('margin', 'exact_score', 'standard_uncertainty_hz')):
            values=np.array([p[field] for p in points], float)
            assert np.isfinite(values).all()
            result['fields'][field]=dict(zip(('min','p10','median','p90','max'),np.quantile(values,[0,.1,.5,.9,1]).tolist()))
            ordered=np.sort(values)
            ax.plot(ordered,np.arange(1,len(values)+1)/len(values),label=row['unit'].split('-')[0])
            ax.set_xlabel(field.replace('_',' ')); ax.set_ylabel('Observation fraction');ax.grid(alpha=.2)
        rows.append(result)
    axes[0].legend()
    fig.suptitle('Recovered detector quality: first single from each dataset (development)')
    fig.tight_layout(); fig.savefig(HERE/'quality-overlay-summary-v1.png',dpi=160);plt.close(fig)
    target=HERE/'quality-overlay-summary-v1.json'
    payload=dict(rows=rows,inputs={str(source):digest(source)},sources={str(Path(__file__).resolve()):digest(__file__)},
                 qualification='Descriptive only. Observations are correlated; uncertainty is heuristic, not measured covariance.')
    with target.open('x') as stream: json.dump(payload,stream,indent=2,allow_nan=False)
    target.with_suffix('.sha256').write_text(digest(target)+'\n')
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
