"""Read existing confirmation IQ with an explicit 8192-window/120-second cap.

The first exporter stopped at6000 windows, before three selected late arcs.
This separate adapter retains the panel selection and source contracts.
"""

import json
from pathlib import Path
import signal
import sys
import numpy as np


def export(case):
    from leo.storage.short_window import ShortWindowReader
    from probe_ds23_shared_probe_cohort import BULK
    from run_algo01_ds23_sample import DATASET, read, sha
    protocol_path = BULK/'IQ/protocol.json'
    protocol = read(protocol_path)
    if sha(DATASET/'manifest.json') != protocol['dataset_manifest_sha256']:
        raise ValueError('dataset manifest changed')
    jobs = [j for j in protocol['jobs'] if j['case'] == case]
    required = {j['visit_index']: j for j in jobs}
    if not jobs or len(required) != len(jobs):
        raise ValueError('unique selected visits required')
    member = next(m for m in read(DATASET/'manifest.json')['members'] if m['dataset_label'] == case)
    def timeout(*_):
        raise TimeoutError('120 second read-only confirmation export budget exhausted')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    arrays, points, manifests, visited = {}, [], [], 0
    try:
        for authority in member['raw_recording']['segments']:
            path = Path(authority['path'])
            if 'sha256:'+sha(path) != authority['sha256']:
                raise ValueError('recording manifest changed')
            reader = ShortWindowReader(path.parent)
            manifests.append(dict(path=str(path), sha256=sha(path)))
            for window in reader.windows():
                visited += 1
                visit = window.index.acquisition['global_visit']
                if visit in required:
                    job = required[visit]
                    if window.index.acquisition['sample_start'] != job['sample_counter']:
                        raise ValueError('original sample counter differs')
                    key = f'window_{visit:06d}'
                    arrays[key] = np.array(window.samples, copy=True)
                    points.append(dict(job, window_key=key,
                                       receiver_offset=reader.manifest.receiver_ids.index(job['native_receiver_id']),
                                       raw_window_sha256=window.index.iq_sha256))
                if len(points) == len(jobs) or visited >= 8192:
                    break
            if len(points) == len(jobs) or visited >= 8192:
                break
        if len(points) != len(jobs):
            raise ValueError('bounded read missing selected late-arc probes')
        metadata = dict(case=case, points=points, sample_rate_hz=reader.manifest.sample_rate_hz,
                        protocol_sha256=sha(protocol_path), recording_manifests=manifests,
                        raw_windows_read=visited, maximum_windows=8192, maximum_seconds=120,
                        explicit_read_cap_extension_from_6000_for_late_arcs=True,
                        selected_raw_window_hashes_verified_by_read_only_adapter=True)
        arrays['metadata_json'] = np.array(json.dumps(metadata))
        np.savez_compressed(sys.stdout.buffer, **arrays)
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    export(sys.argv[1])
