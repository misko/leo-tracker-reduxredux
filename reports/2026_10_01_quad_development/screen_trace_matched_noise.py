"""Fixed-state predictive comparison: tau10 versus trace-matched white noise."""
import fcntl
import json
from pathlib import Path
import sys
import numpy as np
from denser_window_inputs import prepare_denser_window
from denser_track_ports import build_ports
from conditional_track_evidence import nested_transform, conditional_student
from trace_matched_noise import matched_white_variance
from regression_batch import verify_sources
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def main():
    output = HERE/'trace-matched-noise-screen-v1.json'
    if output.exists():
        raise FileExistsError(output)
    parent_path, screen_path = HERE/'added-track-evidence-v1.json', HERE/'added-covariance-screen-v1.json'
    parent, screen = sealed(parent_path), sealed(screen_path)
    for result in (parent, screen):
        verify_sources(result['sources'])
        verify_sources(result['inputs'])
    assert all(r['correlation_time_s'] == 10. for r in screen['selected'])
    previous = {(r['unit'], r['track_index']): r for r in screen['rows']}
    rows, summaries = [], []
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for summary in parent['summary']:
            unit = summary['unit']
            receipt = sealed(HERE/'denser-pilot-v1'/unit/'8'/(unit+'.json'))
            prepared, _ = prepare_denser_window(unit, 8)
            scan, height, _ = prepared[1][0]
            eight, _ = build_ports(scan, height, 8)
            dense, _ = build_ports(scan, height, 16)
            state = np.asarray(receipt['best']['mean'])
            local = []
            for saved in [r for r in parent['rows'] if r['unit'] == unit]:
                i, candidate = saved['track_index'], saved['candidate_index']
                old, port = eight[i], dense[i]
                prediction = port.predict_selected(state, candidate)
                assert prediction.eligible
                transform, _ = nested_transform(old.observation_ids, port.observation_ids,
                    old.likelihood.contrasts, port.likelihood.contrasts)
                b = port.likelihood.contrasts
                contrast = transform@b
                residual = transform@(port.observation-prediction.mean)
                times = port.likelihood.times
                raw = scan.config.white_noise_hz**2*np.eye(len(times))+scan.config.correlated_noise_hz**2*np.exp(-abs(times[:, None]-times[None, :])/10.)
                variance = matched_white_variance(raw, b)
                white = variance*np.eye(len(times))
                trace_error = abs(np.trace(b@(raw-white)@b.T))
                assert trace_error < 1e-7
                scores = {}
                for name, covariance in (('tau10', raw), ('matched_white', white)):
                    scale = contrast@covariance@contrast.T
                    conditional = conditional_student(residual, (scale+scale.T)/2, len(old.observation))
                    assert abs(conditional['log_density']-conditional['log_ratio']) < 1e-8
                    scores[name] = conditional['log_density']
                assert abs(scores['tau10']-previous[(unit, i)]['scores']['10.0']) < 1e-8
                local.append(dict(unit=unit, track_index=i, added_count=saved['added_count'],
                    matched_white_scale_hz=float(np.sqrt(variance)), trace_error=trace_error,
                    baseline=saved['log_predictive_density'], **scores))
            n = sum(r['added_count'] for r in local)
            summaries.append(dict(unit=unit, tracks=len(local), added_count=n,
                tau10_gain_per_point=sum(r['tau10']-r['baseline'] for r in local)/n,
                matched_white_gain_per_point=sum(r['matched_white']-r['baseline'] for r in local)/n,
                tau10_minus_matched_white_per_point=sum(r['tau10']-r['matched_white'] for r in local)/n,
                tau10_wins_tracks=sum(r['tau10'] > r['matched_white'] for r in local),
                median_matched_white_scale_hz=float(np.median([r['matched_white_scale_hz'] for r in local]))))
            rows.extend(local)
    sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
        and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
    result = dict(summary=summaries, rows=rows, sources=sources,
        inputs={str(parent_path): digest(parent_path), str(screen_path): digest(screen_path), **parent['inputs']},
        qualification='Fixed states and identities, no fits/reference scoring. White scale depends only on time design and selected tau10 covariance. Equal total dense contrast scale, not equal individual conditional variances or geographic information.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
