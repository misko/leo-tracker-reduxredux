"""Conditional added-point diagnostics at fixed eight-point states and identities."""
import fcntl
import json
from pathlib import Path
import sys
import time
import numpy as np
from denser_window_inputs import prepare_denser_window
from denser_track_ports import build_ports
from conditional_track_evidence import nested_transform, conditional_student
from regression_batch import verify_sources
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def main():
    output = HERE/'added-track-evidence-v1.json'
    if output.exists():
        raise FileExistsError(output)
    rows, summaries, inputs = [], [], {}
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        for dataset in ('DS9', 'DS10', 'DS11'):
            unit = dataset+'-B01-S1'
            directory = HERE/'denser-pilot-v1'/unit/'8'
            path = directory/(unit+'.json')
            receipt = sealed(path)
            audit_path = directory/'evaluation.json'
            audit = sealed(audit_path)
            assert audit['rows'][0]['accepted'] and audit['rows'][0]['receipt_sha256'] == digest(path)
            freeze = sealed(directory/'sources.json')
            verify_sources(freeze['source_sha256'])
            verify_sources(freeze['inputs'])
            inputs.update({str(p): digest(p) for p in (path, audit_path, directory/'sources.json')})
            prepared, _ = prepare_denser_window(unit, 8)
            scan, height, _ = prepared[1][0]
            eight, _ = build_ports(scan, height, 8)
            sixteen, selection = build_ports(scan, height, 16)
            state = np.asarray(receipt['best']['mean'])
            local = []
            skipped = dict(background=0, no_added_points=0)
            for i, (old, dense, index) in enumerate(zip(eight, sixteen, receipt['best']['associations'])):
                if index == old.candidate_count:
                    skipped['background'] += 1
                    continue
                if len(old.observation_ids) == len(dense.observation_ids):
                    skipped['no_added_points'] += 1
                    continue
                original = old.predict_selected(state, index)
                prediction = dense.predict_selected(state, index)
                transform, added = nested_transform(old.observation_ids, dense.observation_ids,
                    old.likelihood.contrasts, dense.likelihood.contrasts)
                p = len(old.observation)
                residual = transform@(dense.observation-prediction.mean)
                covariance = transform@prediction.covariance@transform.T
                covariance = (covariance+covariance.T)/2
                residual_error = float(np.max(abs(residual[:p]-(old.observation-original.mean))))
                covariance_error = float(np.max(abs(covariance[:p, :p]-original.covariance)))
                assert residual_error < 1e-6 and covariance_error < 1e-7
                conditional = conditional_student(residual, covariance, p)
                ratio_error = abs(conditional['log_density']-conditional['log_ratio'])
                assert ratio_error < 1e-8
                variance = conditional['degrees']/(conditional['degrees']-2)*np.diag(conditional['scale'])
                standardized = conditional['innovation']/np.sqrt(variance)
                signs = np.sign(standardized)
                pairs = int(np.sum(signs[1:]*signs[:-1] != 0))
                same = int(np.sum(signs[1:]*signs[:-1] > 0))
                n = len(signs)
                positive, negative = int(np.sum(signs > 0)), int(np.sum(signs < 0))
                expected_same = (positive*(positive-1)+negative*(negative-1))/(n*(n-1))*(n-1) if n > 1 else 0.
                row = dict(unit=unit, track_index=i, track_id=selection[i]['track_id'], candidate_index=index,
                    original_dimension=p, added_count=len(added), log_predictive_density=conditional['log_density'],
                    conditional_degrees=conditional['degrees'], standardized_innovations=standardized.tolist(),
                    conditional_standard_deviation_hz=np.sqrt(variance).tolist(),
                    added_times_s=dense.likelihood.times[added].tolist(),
                    original_quadratic=conditional['original_quadratic'],
                    marginal_residual_error=residual_error, marginal_covariance_error=covariance_error,
                    density_ratio_error=ratio_error, consecutive_pairs=pairs, same_sign_pairs=same,
                    shuffle_expected_same_sign_pairs=expected_same)
                local.append(row)
            z = np.concatenate([r['standardized_innovations'] for r in local])
            sd = np.concatenate([r['conditional_standard_deviation_hz'] for r in local])
            summary = dict(unit=unit, tracks_total=len(eight), tracks_checked=len(local), skipped=skipped,
                added_observations=len(z), standardized_rms=float(np.sqrt(np.mean(z*z))),
                median_absolute_standardized_innovation=float(np.median(abs(z))),
                fraction_absolute_over_2=float(np.mean(abs(z)>2)),
                median_conditional_sd_hz=float(np.median(sd)),
                predictive_nats_per_added_point=sum(r['log_predictive_density'] for r in local)/len(z),
                consecutive_pairs=sum(r['consecutive_pairs'] for r in local),
                same_sign_pairs=sum(r['same_sign_pairs'] for r in local),
                shuffle_expected_same_sign_pairs=sum(r['shuffle_expected_same_sign_pairs'] for r in local),
                maximum_density_ratio_error=max(r['density_ratio_error'] for r in local),
                maximum_marginal_covariance_error=max(r['marginal_covariance_error'] for r in local))
            rows.extend(local)
            summaries.append(summary)
        sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
            and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
        result = dict(summary=summaries, rows=rows, inputs=inputs, sources=sources, seconds=time.monotonic()-started,
            qualification='Fixed eight-point fitted states/identities. Signal-assigned tracks with added evidence only; background skips explicit. Exact conditional Student density given plug-in state, not marginalized state uncertainty or independent emitter truth. No fits, deletions or reference-error selection. Descriptive dependent sign pairs, not an iid significance test.')
        with output.open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        output.with_suffix('.sha256').write_text(digest(output)+'\n')
        print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
