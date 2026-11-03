"""Exact reference-identity marginals at saved estimates, with parity audits."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT / 'acquisition_position'))
from common import JOBS, base, read, digest, fast, verify_sources
from fit import load
from source_partition_fast import partition
from probes import probe


def main(cohort, index):
    started = time.monotonic()
    old, initial, sources = load(cohort, index, 'signed')
    reference = {}
    for tid, track in old.tracks.items():
        predicted, visible = old.geometry.prediction(track, initial)
        scores, _, audits, _ = fast.profile(track['y'][None] - predicted, track['mask'])
        assert all(a['converged'] for a in audits)
        scores = np.where(visible, scores, -np.inf)
        probabilities = np.exp(scores - logsumexp(scores))
        slot = int(np.argmax(probabilities))
        reference[tid] = dict(norad=old.meta[tid]['candidate_norad'][slot], original_probability=float(probabilities[slot]), rf_hz=old.meta[tid]['rf_hz'], receiver=old.meta[tid]['receiver'])
    spec = importlib.util.spec_from_file_location('whole_source_posterior_probe', PARENT / 'whole_source_position.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bound = read(PARENT / 'acquisition_position' / f'input-{cohort}-{index:02d}.json')
    config = read(base(cohort) / 'plan.json')['config']
    models = {}
    for name, folder, arm in [('doppler', 'association_only', 'doppler'), ('joint', 'acquisition_position', 'signed'), ('frozen', 'association_only', 'signed')]:
        fitpath = PARENT / folder / f'fit-{cohort}-{index:02d}-{arm}.json'
        fit = read(fitpath)
        verify_sources(fit)
        sources[str(fitpath)] = digest(fitpath)
        model = module.WholeSourcePosition(old.geometry.document, config, bound, old.calibration, arm)
        if name == 'frozen':
            fixed = {tid: model.receiver_probabilities(track, tid, initial) for tid, track in model.tracks.items()}
            model.receiver_probabilities = lambda track, tid, x: fixed[tid]
        contexts = []
        for lane in model.lanes:
            tids = sorted(lane['left'] + lane['right'])
            candidates = sorted({c for t in tids for c in model.meta[t]['candidate_norad']})
            contexts.extend((lane['rf_hz'], tids, candidates) for _ in lane['ownership_alternatives'])
        captured = []
        def capture(n, factors):
            rf, tids, candidates = contexts[len(captured)]
            score, gradient, result = probe(n, factors, candidates, [reference[t]['norad'] for t in tids])
            captured.append(dict(rf_hz=rf, tids=tids, **result))
            return score, gradient
        module.partition = partition
        unprobed = model.evaluate(fit['x'], gradient=False, force_partition=True)
        module.partition = capture
        value = model.evaluate(fit['x'], gradient=False, force_partition=True)
        parity = dict(score=abs(value['score'] - unprobed['score']), expected_sources=abs(value['expected_sources'] - unprobed['expected_sources']))
        assert parity['score'] <= 1e-8 and parity['expected_sources'] <= 1e-7
        assert len(captured) == len(contexts)
        tracks, entropy = {}, 0.
        offset = 0
        for lane, result in zip(model.lanes, value['lanes'], strict=True):
            count = len(lane['ownership_alternatives'])
            branches = captured[offset:offset + count]
            offset += count
            weights = np.array(result['ownership_posterior'])
            p = weights @ np.stack([b['reference_probability'] for b in branches])
            for tid, probability in zip(branches[0]['tids'], p, strict=True):
                assert tid not in tracks
                tracks[tid] = float(probability)
            entropy += float(weights @ np.array([b['entropy'] for b in branches]))
            positive = weights > 0
            entropy -= float(weights[positive] @ np.log(weights[positive]))
        models[name] = dict(qualified=fit['qualified'], reference_probability=tracks, entropy_nats=entropy, expected_different_identities=float(sum(1 - p for p in tracks.values())), parity=parity)
    sources.update({str(p): digest(p) for p in (Path(__file__), HERE / 'probes.py', HERE / 'test_probes.py', HERE / 'PROTOCOL.md')})
    result = dict(cohort=cohort, index=index, reference=reference, models=models, sources=sources, elapsed_s=time.monotonic() - started)
    with (HERE / f'diagnostic-{cohort}-{index:02d}.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(cohort=cohort, index=index, tracks=len(reference), models={k: {a: b for a, b in v.items() if a != 'reference_probability'} for k, v in models.items()}, elapsed_s=result['elapsed_s'])), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
