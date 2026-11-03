"""Exact posterior audit of every likelihood-ratio result, without refitting."""
import json
from pathlib import Path
import sys
import time
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'acquisition_position'))
sys.path.insert(0, str(HERE.parent / 'posterior_diagnostic'))
sys.path.insert(0, str(HERE.parent / 'temporal_whole'))
from common import JOBS, base, read, digest, verify_sources
from fit import load
from probes import probe
import ratio_model as time_model
from source_partition_fast import partition


def main(cohort, index):
    started = time.monotonic()
    fitpath = HERE / f'fit-{cohort}-{index:02d}-candidate.json'
    referencepath = HERE.parent / 'posterior_diagnostic' / f'diagnostic-{cohort}-{index:02d}.json'
    fit, reference_doc = read(fitpath), read(referencepath)
    verify_sources(fit)
    verify_sources(reference_doc)
    old, _, sources = load(cohort, index, fit['selected_arm'])
    bound = read(HERE.parent / 'acquisition_position' / f'input-{cohort}-{index:02d}.json')
    model = time_model.GeometryRatioPosition(old.geometry.document, read(base(cohort) / 'plan.json')['config'], bound, old.calibration, fit['selected_arm'], fit['tau_s'])
    reference = reference_doc['reference']
    contexts = []
    for lane in model.lanes:
        tids = sorted(lane['left'] + lane['right'])
        candidates = sorted({c for t in tids for c in model.meta[t]['candidate_norad']})
        contexts.extend((tids, candidates) for _ in lane['ownership_alternatives'])
    captured = []
    def capture(n, factors):
        tids, candidates = contexts[len(captured)]
        score, gradient, result = probe(n, factors, candidates, [reference[t]['norad'] for t in tids])
        captured.append(dict(tids=tids, **result))
        return score, gradient
    unprobed = model.evaluate(fit['x'], gradient=False, force_partition=True)
    time_model.partition = capture
    try:
        value = model.evaluate(fit['x'], gradient=False, force_partition=True)
    finally:
        time_model.partition = partition
    assert abs(value['score'] - unprobed['score']) < 1e-8
    assert abs(value['expected_sources'] - unprobed['expected_sources']) < 1e-7
    probabilities, entropy, offset = {}, 0., 0
    for lane, result in zip(model.lanes, value['lanes'], strict=True):
        count = len(lane['ownership_alternatives'])
        branches = captured[offset:offset + count]
        offset += count
        weights = np.array(result['ownership_posterior'])
        p = weights @ np.stack([b['reference_probability'] for b in branches])
        probabilities.update({t: float(v) for t, v in zip(branches[0]['tids'], p, strict=True)})
        entropy += float(weights @ np.array([b['entropy'] for b in branches]))
        positive = weights > 0
        entropy -= float(weights[positive] @ np.log(weights[positive]))
    assert offset == len(contexts)
    sources.update({str(p): digest(p) for p in (Path(__file__), fitpath, referencepath, HERE.parent / 'posterior_diagnostic/probes.py')})
    result = dict(cohort=cohort, index=index, qualified=fit['qualified'], fallback=fit['fallback'], reference_probability=probabilities, entropy_nats=entropy, lost_majority=sum(p < .5 for p in probabilities.values()), high_confidence_lost_majority=sum(reference[t]['original_probability'] >= .99 and p < .5 for t, p in probabilities.items()), expected_different_identities=float(sum(1 - p for p in probabilities.values())), sources=sources, elapsed_s=time.monotonic() - started)
    with (HERE / f'posterior-{cohort}-{index:02d}.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k not in ('reference_probability', 'sources')}), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
