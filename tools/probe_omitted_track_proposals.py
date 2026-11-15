"""Replay at most four saved contexts and nominate omitted tracks without fitting.

Default invocation writes only a plan. Each executed context must reproduce its
saved c0 and fitted-c objectives before the selector runs. No annotation,
position optimization or new observations are requested. Reference coordinates
never enter the selector.
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from census_algo07v5_initial_controls import fingerprint
from probe_algo07v5_annotation_rounds import load_context, request_inputs

from leo.analysis.localization_v3 import omitted_track_proposals
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import stage_deadline


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 121), default=120)
    parser.add_argument('--max-proposals', type=int, choices=(1, 2), default=2)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if (output.exists() or output.is_relative_to('/mnt/qnap01')
            or not 1 <= len(args.request) <= 4):
        parser.error('Fresh local output and one to four stored requests required')
    records = [request_inputs(path) for path in args.request]
    if len({canonical_digest(request) for request, _, _ in records}) != len(records):
        parser.error('Stored requests must be distinct')
    source_paths = [Path(__file__), Path(omitted_track_proposals.__file__),
                    Path(__file__).with_name('probe_algo07v5_annotation_rounds.py'),
                    Path(__file__).with_name('census_algo07v5_initial_controls.py'),
                    *args.request]
    sources = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    plan = dict(status='plan', policy=omitted_track_proposals.POLICY,
                max_proposals=args.max_proposals, timeout_per_context_s=args.timeout,
                sources=sources, affinity=sorted(os.sched_getaffinity(0)),
                BLAS_threads=os.environ.get('OPENBLAS_NUM_THREADS'),
                cases=[dict(request_path=str(path.resolve()), request_sha256=canonical_digest(r),
                            identity=j['identity'])
                       for path, (r, j, _) in zip(args.request, records, strict=True)],
                GPS_used=False, future_TLE_used=False, position_fit_performed=False,
                predictive_qualification_performed=False, position_inclusion_authorized=False)
    output.mkdir(parents=True)

    def save(name, value):
        (output / name).write_text(json.dumps(
            value, indent=2, default=_json_value, allow_nan=False) + '\n')

    save('plan.json', plan)
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    if len(os.sched_getaffinity(0)) != 1 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        raise ValueError('Pin one CPU and one BLAS thread')
    rows = []
    for index, (request, job, store) in enumerate(records):
        began = time.perf_counter()
        try:
            with stage_deadline(args.timeout):
                context, evidence, binding = load_context(request, job, store, None)
                before = fingerprint(evidence)
                start = time.perf_counter()
                selection = omitted_track_proposals.rank_omitted_tracks(
                    context, evidence, max_proposals=args.max_proposals)
                seconds = time.perf_counter() - start
                if fingerprint(evidence) != before:
                    raise ValueError('Selector changed saved recovery evidence')
                if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest
                       for p, digest in sources.items()):
                    raise ValueError('Probe source or saved request changed during execution')
                row = dict(status='complete', identity=job['identity'], binding=binding,
                           selector=selection, selector_seconds=seconds,
                           elapsed_seconds=time.perf_counter() - began,
                           GPS_used=False, position_fit_performed=False,
                           predictive_qualification_performed=False,
                           position_inclusion_authorized=False)
        except Exception as error:
            row = dict(status='failed', identity=job['identity'],
                       error_type=type(error).__name__, error=str(error),
                       elapsed_seconds=time.perf_counter() - began)
        rows.append(row)
        save(f'context-{index}.json', row)
        print(json.dumps(dict(index=index, status=row['status'], identity=job['identity'],
                              selector_seconds=row.get('selector_seconds'),
                              selected_track_ids=[t['track_id'] for t in
                                                  row.get('selector', {}).get('targets', [])],
                              error=row.get('error'))), flush=True)
    save('result.json', dict(status='complete' if all(r['status'] == 'complete' for r in rows)
                             else 'failed', policy=omitted_track_proposals.POLICY, cases=rows))
    return 0 if all(r['status'] == 'complete' for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
