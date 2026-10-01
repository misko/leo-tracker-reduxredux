"""No-refit predictive comparison on immutable residual statistics."""
from pathlib import Path
import fcntl
import numpy as np
from run_window import prepare_window
from check_receiver_curvature import save
from regression_batch import verify_sources
from screen_seed_prefix import sealed, digest
from scale_mixture import mixture, held_prediction

HERE = Path(__file__).resolve().parent


def main():
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inputs = {}; rows = []
        source = sealed(HERE/'scale-prediction-summary-v1.json')
        inputs[str(HERE/'scale-prediction-summary-v1.json')] = digest(HERE/'scale-prediction-summary-v1.json')
        verify_sources(source['sources']); verify_sources(source['inputs'])
        sources = {str(HERE/name): digest(HERE/name) for name in ('SCALE_MIXTURE_PLAN.md', 'scale_mixture.py', 'scale_prediction.py', 'test_scale_mixture.py', 'check_scale_mixture.py')}
        for parent in source['rows']:
            directory = HERE/'scale-prediction-v1'/parent['unit']
            freeze = sealed(directory/'sources.json'); verify_sources(freeze['source_sha256']); verify_sources(freeze['inputs'])
            for name in ('sources.json', 'result.json'): inputs[str(directory/name)] = digest(directory/name)
            assert sealed(directory/'result.json') == parent
            tracks = []; maximum = 0.
            for held in parent['tracks']:
                training = [r for r in parent['tracks'] if r['norad'] == held['norad'] and r['track_index'] != held['track_index']]
                value, probability = held_prediction(held, training)
                difference = mixture(training+[held])-mixture(training)
                error = abs(value-difference); assert error < 1e-9; maximum = max(maximum, error)
                gain = value-held['independent']
                if not training: assert abs(gain) < 1e-10
                tracks.append(dict(track_index=held['track_index'], norad=held['norad'], dimension=held['d'],
                    training_tracks=len(training), training_shared_probability=probability,
                    independent=held['independent'], shared=held['shared_predictive'], mixture=value,
                    mixture_gain=gain, shared_gain=held['gain'], gain_per_contrast=gain/held['d']))
            multi = [r for r in tracks if r['training_tracks']]
            pooled = sum(r['mixture_gain'] for r in multi)/sum(r['dimension'] for r in multi)
            median = float(np.median([r['gain_per_contrast'] for r in multi]))
            row = dict(unit=parent['unit'], tracks=tracks, multi_track_count=len(multi),
                pooled_mixture_gain=pooled, median_mixture_gain=median, pooled_shared_gain=parent['pooled_gain_per_contrast'],
                improving_tracks=sum(r['mixture_gain'] > 0 for r in multi),
                mixture_vs_shared_gain=sum(r['mixture']-r['shared'] for r in multi)/sum(r['dimension'] for r in multi),
                maximum_formula_difference=maximum, gate_passed=bool(pooled > 0 and median > 0))
            rows.append(row)
        verify_sources(sources); verify_sources(inputs)
        output = HERE/'scale-mixture-prediction-v1.json'
        save(output, dict(rows=rows, gate_passed=all(r['gate_passed'] for r in rows), inputs=inputs, sources=sources,
            qualification='Equal-prior conditional group mixture on exposed fixed residuals. No fit, geographic scoring or independent validation.'))
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
        x = np.arange(3)
        ax.bar(x-.18, [r['pooled_shared_gain'] for r in rows], .36, label='Full sharing')
        ax.bar(x+.18, [r['pooled_mixture_gain'] for r in rows], .36, label='Equal-prior mixture')
        ax.axhline(0, color='gray', linewidth=.8); ax.set_xticks(x, ['DS9', 'DS10', 'DS11'])
        ax.set_ylabel('Pooled held-track log-score gain / contrast'); ax.set_title('Conditional scale prediction versus independent Student-t4')
        ax.legend(); ax.grid(axis='y', alpha=.2); fig.savefig(output.with_suffix('.png'), dpi=160)
        for r in rows: print({k:v for k,v in r.items() if k != 'tracks'})


if __name__ == '__main__': main()
