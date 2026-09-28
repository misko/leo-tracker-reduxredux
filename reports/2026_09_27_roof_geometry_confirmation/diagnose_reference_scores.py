"""Post-unblinding oracle diagnostic, NEVER a search or estimator input.

Uses the frozen model at the reference and fixed neighboring coordinates to
distinguish missed coverage from objective misranking. Does not modify searches.
"""
import argparse
import json
from pathlib import Path
import pickle
import numpy as np
import run_topology_confirmation as frozen

HERE = Path(__file__).resolve().parent
base = frozen.base


def profile_offsets():
    return [(0., 0.)] + [(e*r, n*r) for r in (1.5625, 5., 25.)
                        for e, n in ((1., 0.), (-1., 0.), (0., 1.), (0., -1.))]


def classify(selected_score, reference_score, tolerance=1e-9):
    gap = selected_score-reference_score
    return ('reference_better_search_missed_it' if gap > tolerance else
            'selected_better_than_reference' if gap < -tolerance else 'indistinguishable')


def run(index):
    entries, manifest_sha, _ = frozen.original.confirmation_entries()
    entry = entries[index]; sid = entry['session_id']
    target = HERE/f'reference-diagnostic-{sid}.json'
    if target.exists():
        raise FileExistsError(target)
    # Require whole-cohort unblinding, not partial peeking.
    report = json.loads((HERE/'topology_distance_results.json').read_text())
    assert report['complete'] and report['frozen_inputs']['manifest_sha256'] == manifest_sha
    result_bytes = (HERE/f'topology-search-{sid}.json').read_bytes()
    assert base.digest(result_bytes) == report['search_artifact_sha256'][sid]
    result = json.loads(result_bytes)
    audit, audit_sha = frozen.frozen_audit()
    frequency, detection, continuous, variance, bias, models = frozen.frozen_models(audit, audit_sha)
    assert all(result[key] == value for key, value in models.items())
    payload = Path(entry['cache_file']).read_bytes()
    assert base.digest(payload) == entry['cache_sha256']
    raw = pickle.loads(payload)
    prepared = base.prepare_adaptive_tle_position_inputs(sid, inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path('/var/lib/leo/tle')))
    assert prepared.input_manifest_sha256 == entry['input_manifest_sha256']
    assert prepared.analysis_manifest_sha256 == entry['analysis_manifest_sha256']
    prepared, receipt = frozen.filter_prepared(prepared, frozen.resolve(raw))
    assert receipt == result['topology_receipt']
    rows = frozen.original.reception_endpoints.build(raw, prepared, bias_hz=bias)
    reception, _ = frozen.original.reception_inputs(prepared, rows, detection, continuous)
    banks, _ = base.build_prediction_banks(prepared.catalogue, prepared.candidate_indices,
        prepared.start_utc_ns, prepared.tracks, taus_s=np.array([0.]))
    manifest = json.loads((HERE/'manifest.json').read_text())
    item = next(x for x in manifest['sessions'] if x['pose']['session_id'] == sid)
    pose = item['pose']['pose_authority']
    origin = (pose['latitude_deg'], pose['longitude_deg'])
    evaluator = frozen.original.RobustBranchEvaluator(banks, origin, reception, variance, frequency['parameters'])
    profile = [evaluator.evaluate(*offset) for offset in profile_offsets()]
    reference = profile[0]
    comparisons = []
    for prior, branch in result['branches'].items():
        for arm, output in branch['arms'].items():
            selected = output['selected']
            # Independently reproduce the saved selected location, without borrowing
            # fitted IDs/weights or initializing from the reference shortlist.
            check = frozen.original.RobustBranchEvaluator(banks,
                (selected['latitude_deg'], selected['longitude_deg']), reception, variance, frequency['parameters'])
            reproduced = check.evaluate(0., 0.)
            for score in selected['scores']:
                assert np.isclose(reproduced['scores'][score], selected['scores'][score], rtol=0, atol=1e-7)
            s, r = selected['scores'][arm], reference['scores'][arm]
            comparisons.append(dict(prior=prior, arm=arm, selected_score=s,
                reference_score=r, selected_minus_reference=s-r, diagnosis=classify(s, r)))
    out = dict(session_id=sid, complete=True,
        scope='Post-hoc reference-centered oracle score diagnostic. Not an estimator, confirmation improvement, or shared-prior initialization.',
        search_sha256=base.digest(result_bytes), topology_audit_sha256=audit_sha,
        model_hashes=models, source_sha256=base.digest(Path(__file__).read_bytes()),
        reference_latitude_longitude=origin, profile=profile, comparisons=comparisons)
    base.atomic(target, out)
    print(json.dumps(dict(session_id=sid, comparisons=comparisons), indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan-index', type=int, required=True, choices=range(4))
    run(parser.parse_args().scan_index)
