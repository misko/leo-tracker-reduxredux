"""Bind the capped initial likelihood to its source track and render diagnostics."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import hierarchical, position
from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.storage.localization_v3 import LocalizationV3Store

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    output = Path(__file__).resolve().parent
    base = Path('/srv/bulk/leo-dev')
    capture = base/'algo07v3-initial-capture-20261106/fitted_c-capture'
    meta = json.loads((capture/'hardest.json').read_bytes())
    raw = capture/'hardest.npz'
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == meta['arrays_sha256']
    with np.load(raw, allow_pickle=False) as archive:
        args = [archive[f'argument_{i}'] for i in range(4)]
    assert meta['scalar_keywords'] == {}
    request_path = base/'algo07v3-control-view-native-0066-20261106/candidate-request.json'
    request = json.loads(request_path.read_bytes())
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared = saved['evidence']['preparation']
    choice = saved['evidence']['audit']['initial']['choices'][1]
    noise = (json.dumps(prepared['noise'], default=_json_value,
                        sort_keys=True, allow_nan=False)+'\n').encode()
    scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                    hashlib.sha256(noise).hexdigest(), genuine=False)
    reference = choice['arms']['fitted_c']['phase_rounds'][meta['phase']]['phase_reference']
    problem = position.NormalPosition(scan, choice['node'], scan.radio_sigma_hz,
                                      True, reference=reference)
    original = position.hierarchical_bound
    verified = []
    def verify(*a, **kw):
        assert fingerprint((a, kw)) == fingerprint((args, {}))
        result = original(*a, **kw)
        encoded = json.dumps(fingerprint(result), sort_keys=True).encode()
        signature = hashlib.sha256(encoded).hexdigest()
        assert signature == meta['result_signature']
        verified.append(True)
        return result
    position.hierarchical_bound = verify
    try:
        problem.calculate([float.fromhex(x) for x in meta['position']])
    finally:
        position.hierarchical_bound = original
    assert verified == [True]
    result = hierarchical.hierarchical_bound(*args)
    trajectory_path = base/'algo07v3-initial-trajectory-20261106/result.json'
    trajectory = json.loads(trajectory_path.read_bytes())
    assert trajectory['exact'] and trajectory['unchanged_inputs']
    updates = np.array([r['noise_log_change'] for r in trajectory['rows']])
    winners = np.abs(updates).argmax(axis=1)
    indices, counts = np.unique(winners, return_counts=True)
    ranked = sorted(zip(indices.tolist(), counts.tolist(), strict=True), key=lambda x:-x[1])
    ids, groups = np.unique(args[3], return_inverse=True)
    tracks = []
    for group, count in ranked:
        member = int(ids[group])
        index = problem.members[member]
        track = scan.tracks[index]
        select = groups == group
        catalogue_index = problem.rows[member]['candidate_index']
        tracks.append(dict(group=group, dominant_iterations=count, track_index=index,
                           key=track['key'], receiver=track['receiver'], channel=track['channel'],
                           start_s=track['start_s'], end_s=track['end_s'], points=int(select.sum()),
                           hypothesis_norad=int(scan.norads[catalogue_index]),
                           polynomial_rms_hz=track['residual_rms_hz'],
                           final_model_rms_hz=float(np.sqrt(np.mean(result['conditional_residual_hz'][select]**2))),
                           final_precision=float(result['noise_precision'][group]),
                           final_log_change=float(updates[-1, group])))
    # This diagnostic reconstructs posterior Grams at three already observed
    # states; it does not feed a changed solve into either fit or association.
    y, features, sigma, _ = args
    standardized = features/np.broadcast_to(sigma, y.shape)[:, None]
    alpha = 2 + np.bincount(groups)/2
    blocks = []
    for group in range(len(ids)):
        use = groups == group
        columns = np.flatnonzero(np.any(standardized[use] != 0, axis=0))
        local = standardized[use][:, columns]
        blocks.append((columns, local.T@local))
    minimum = int(np.abs(updates).max(axis=1).argmin())
    conditions = []
    for iteration in (0, minimum, len(updates)-1):
        weights = alpha/np.array(trajectory['rows'][iteration]['rate'])
        gram = np.eye(features.shape[1])
        for weight, (columns, block) in zip(weights, blocks, strict=True):
            gram[np.ix_(columns, columns)] += weight*block
        eigen = np.linalg.eigvalsh(gram)
        conditions.append(dict(iteration=iteration, condition=float(eigen[-1]/eigen[0]),
                               smallest_eigenvalue=float(eigen[0]),
                               largest_eigenvalue=float(eigen[-1])))
    profiles = {}
    for name, source in (
        ('initial-fit', base/'algo07v3-initial-capture-20261106/result.json'),
        ('initial-parts', base/'algo07v3-initial-parts-20261106/result.json'),
        ('initial-trajectory', trajectory_path),
        ('initial-layout', base/'algo07v3-root-layout-initial-20261106/result.json'),
        ('recovery-layout', base/'algo07v3-root-layout-recovery-20261106/result.json')):
        data = source.read_bytes()
        (output/f'{name}.json').write_bytes(data)
        profiles[name] = dict(source=str(source), sha256=hashlib.sha256(data).hexdigest())
    parts = json.loads((output/'initial-parts.json').read_bytes())
    total = sum(r['seconds'] for r in parts['trials'])
    shares = {k:100*v['seconds']/total for k,v in parts['parts'].items()}
    layout = {}
    for name in ('initial', 'recovery'):
        data = json.loads((output/f'{name}-layout.json').read_bytes())
        means = {side: float(np.mean([r['seconds'] for r in data['rows'] if r['side']==side]))
                 for side in ('baseline', 'candidate')}
        layout[name] = dict(exact=data['exact'], **means,
                            change_pct=100*(means['candidate']/means['baseline']-1))
    summary = dict(track_mapping_verified=True, input_capture=str(capture),
                   analysis_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   capture_sha256=meta['arrays_sha256'], scientific_receipt=saved['sha256'],
                   profiles=profiles, tracks=tracks, conditions=conditions,
                   precision_minimum_iteration=minimum, parts_pct=shares, layout=layout,
                   adopted=False, full_pipeline_speedup=None)
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for track in tracks[:2]:
        label = f"Group {track['group']}: RX{track['receiver']} CH{track['channel']}"
        axes[0].semilogy(np.abs(updates[:,track['group']]), label=label)
    axes[0].semilogy(np.abs(updates).max(axis=1), '--', color='black',
                     alpha=.5, label='Maximum update')
    axes[0].axhline(1e-5, color='red', linestyle=':', label='Existing stopping threshold')
    axes[0].set(xlabel='Precision iteration (zero-based)',
                ylabel='Absolute log noise-precision update',
                title='One group dominates 242 / 256 iterations')
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=.2)
    labels = ['Inverse solve','Covariance product','Lower LU','Cholesky','Assembly','Other']
    names = ('inverse_solve', 'covariance_product', 'lower_LU', 'cholesky', 'ordered_assembly')
    values = [shares[k] for k in names]
    values.append(100-sum(values))
    axes[1].barh(labels[::-1], values[::-1], color='#4477aa')
    axes[1].set(xlabel='Share of instrumented likelihood time (%)',
                title='Same numerical bottleneck as recovery')
    fig.suptitle('DS26-0066 initial branch 1, fitted c, second phase: first capped likelihood')
    fig.savefig(output/'diagnosis.png', dpi=150)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
