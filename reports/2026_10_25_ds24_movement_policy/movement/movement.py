"""One bounded sealed case/seed/fold job; launched only by the approved batch."""
import argparse
import hashlib
import os
import resource
import signal
import time
import traceback
from pathlib import Path

import numpy as np

from common import (ARMS, MODELS, digest, finite_numeric_tree, job_key, load_sealed,
    read, require_job, result_path, value_digest, verify_bindings, write_new)
from kernel import build, causal_reference, cold_fit, family_partition, score_endpoint, training_data
from matched_controls import load_baseline, measurement_binding
from policy import job_failures


def one(root, case, seed, fold):
    root = Path(root).resolve()
    protocol = load_sealed(root)
    require_job(protocol, case, seed, fold)
    protocol_sha256 = digest(root/'protocol.json')
    destination = result_path(root, case, seed, fold)
    if destination.exists():
        raise ValueError('refuse to overwrite job evidence')
    key = job_key(case, seed, fold)
    write_new(root/'claims'/(key+'.json'), dict(case=case, seed=seed, fold=fold, pid=os.getpid(), protocol_sha256=protocol_sha256))
    began = time.monotonic()
    result = dict(case=case, seed=seed, fold=fold, GPS_used=False, protocol_sha256=protocol_sha256,
        source_sha256=digest(__file__), kernel_sha256=digest(Path(__file__).with_name('kernel.py')), arms={})
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('240 second sealed fold cap')))
    signal.alarm(protocol['job_seconds_cap'])
    try:
        sealed = read(root/'input_manifest.json')[case]
        verify_bindings(sealed['file_bindings'])
        d = load_baseline(case)
        binding = measurement_binding(d)
        if binding != sealed['measurement_binding_sha256'] or d['baseline_sha256'] != sealed['baseline_sha256']:
            raise ValueError('loaded inputs differ from sealed measurement binding')
        partition = family_partition(d, seed)
        frozen_partition = sealed['partitions'][str(seed)]
        if partition['permutation'] != frozen_partition['permutation'] or partition['active_family_indices'] != frozen_partition['active_family_indices']:
            raise ValueError('family permutation differs from frozen partition')
        held = partition['folds'][fold]
        frozen_fold = frozen_partition['folds'][fold]
        if held != frozen_fold['held_families']:
            raise ValueError('held family assignment changed')
        train = training_data(d, held)
        p = build(train, 'c0', causal_reference(train, held), 'baseline')
        original_ids = [oid for i in p.members for oid in p.scan.tracks[i]['observation_ids']]
        train_ids = np.asarray(original_ids)[train['keep']].tolist()
        train_ids.extend(oid for entry in train['entries'] for oid in entry['observation_ids'])
        if value_digest(train_ids) != frozen_fold['training_ids_sha256']:
            raise ValueError('training native IDs differ from sealed partition')
        result.update(held_families=held, held_norads=frozen_fold['held_norads'],
            input_binding_sha256=binding, baseline_sha256=d['baseline_sha256'],
            training_ids_sha256=value_digest(train_ids), held_ids_sha256=frozen_fold['held_ids_sha256'])
        for arm in ARMS:
            analysis = dict(fits={}, crossover={})
            result['arms'][arm] = analysis
            for model in MODELS:
                analysis['fits'][model] = cold_fit(train, held, arm, model)
            for predictor in MODELS:
                analysis['crossover'][predictor] = {}
                for endpoint in MODELS:
                    artifact = root/'arrays'/f'{key}_{arm}_{predictor}_at_{endpoint}.npz'
                    prediction = score_endpoint(d, train, held, arm, predictor,
                        analysis['fits'][endpoint]['endpoint_east_north_km'], artifact)
                    if prediction['observation_id_sha256'] != frozen_fold['held_ids_sha256']:
                        raise ValueError('held native IDs differ from sealed partition')
                    analysis['crossover'][predictor][endpoint] = prediction
        if measurement_binding(d) != binding or not finite_numeric_tree(result):
            raise ValueError('mutated inputs or nonfinite scientific calculations')
        verify_bindings(sealed['file_bindings'])
        load_sealed(root)
        result['status'] = 'complete'
        result['convergence_or_validity_failures'] = job_failures(result)
    except Exception as exc:
        result.update(status='timeout' if isinstance(exc, TimeoutError) else 'failed',
            error=repr(exc), traceback=traceback.format_exc())
    finally:
        signal.alarm(0)
    result.update(seconds=time.monotonic()-began, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    write_new(destination, result)
    print(key, result['status'], 'seconds', round(result['seconds'], 2), 'rssKiB', result['peak_rss_kib'], flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--fold', type=int, required=True)
    args = parser.parse_args()
    one(args.root, args.case, args.seed, args.fold)
