"""Stage and atomically publish the already-frozen full193 geographic report.

This is a separate postseal entrypoint. It must not be invoked during numerical
execution and does not change the frozen evaluation or numerical sources.
"""

import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from PIL import Image

import evaluation
import postseal_preflight
import publish
import report
import report_metrics


HERE = Path(__file__).resolve().parent
FINAL_NAME = 'sealed-full193-report'
ARTIFACTS = ('protocol.json', 'evaluation_protocol.json', 'SUMMARY.json',
             'METRICS.json', 'RESULTS.md', 'paired-position.png',
             'error-ecdf.png', 'c-contrast.png', 'member-errors.png',
             'PROVENANCE.json')
IMAGES = ('paired-position.png', 'error-ecdf.png', 'c-contrast.png',
          'member-errors.png')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _write_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def _rename_noreplace(source, target):
    """Linux same-directory atomic rename, refusing even an empty destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = libc.renameat2
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                          ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(code, os.strerror(code), str(target))
        raise OSError(code, os.strerror(code), str(target))


def _verify_stage(stage, summary, metrics):
    _require(all((stage / name).is_file() for name in ARTIFACTS),
             'staged report artifact missing')
    _require(_read_json(stage / 'SUMMARY.json') == summary,
             'staged summary differs')
    _require(_read_json(stage / 'METRICS.json') == metrics,
             'staged metrics differ')
    markdown = (stage / 'RESULTS.md').read_text()
    _require(markdown.strip() and all('(' + name + ')' in markdown for name in IMAGES),
             'report markdown missing image links')
    for name in IMAGES:
        path = stage / name
        with Image.open(path) as image:
            _require(image.format == 'PNG' and min(image.size) > 0,
                     'invalid PNG: ' + name)
            image.verify()
        with Image.open(path) as image:
            image.load()


def _read_json(path):
    return json.loads(path.read_text())


def run(*, here=HERE):
    """Return final directory only after all proofs, rendering and rename pass."""
    here = Path(here)
    destination = here / FINAL_NAME
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Final report already exists: ' + str(destination))
    plan = _read_json(here / 'protocol.json')
    frozen_evaluation = _read_json(here / 'evaluation_protocol.json')
    _require(report.prepare_evaluation() == frozen_evaluation,
             'frozen evaluation metadata differs')
    _require(sys.executable == plan['runtime']['interpreter'],
             'pinned reporting interpreter required')
    _require(evaluation.sha(here / 'protocol.json') == report.NUMERICAL_SHA,
             'frozen numerical protocol bytes differ')
    _require(frozen_evaluation['numerical_protocol_digest'] == report.NUMERICAL_DIGEST,
             'frozen numerical digest differs')
    preflight = postseal_preflight.preflight(plan, here / 'results',
                                             report.NUMERICAL_DIGEST)
    _require(preflight['counts']['members'] == 193
             and preflight['counts']['phases'] == 579,
             'postseal provenance coverage differs')
    summary = evaluation.build(plan, here / 'results', report.NUMERICAL_DIGEST)
    _require(summary.get('all_terminal') is True
             and len(summary.get('rows', [])) == 193,
             'full193 geographic summary missing')
    _require(summary.get('receipt_sha256') == preflight['receipt_sha256'],
             'receipts changed between preflight and evaluation')
    metrics = report_metrics.aggregate(plan['members'], summary['rows'])
    _require(metrics.get('membership') == 193,
             'full193 metrics missing')

    stage = Path(tempfile.mkdtemp(prefix='.' + FINAL_NAME + '-stage-', dir=here))
    try:
        shutil.copyfile(here / 'protocol.json', stage / 'protocol.json')
        shutil.copyfile(here / 'evaluation_protocol.json',
                        stage / 'evaluation_protocol.json')
        _write_json(stage / 'SUMMARY.json', summary)
        images = publish.publish(summary, metrics, stage)
        _require({Path(path).name for path in images} == set(IMAGES),
                 'renderer returned unexpected image inventory')
        provenance = dict(
            scope='Consumed full193 single-pass diagnostic; no deployment parity',
            runtime_interpreter=sys.executable,
            numerical_protocol_sha256=evaluation.sha(here / 'protocol.json'),
            evaluation_protocol_sha256=evaluation.sha(here / 'evaluation_protocol.json'),
            numerical_protocol_digest=report.NUMERICAL_DIGEST,
            preflight_counts=preflight['counts'],
            receipt_inventory_sha256='sha256:' + hashlib.sha256(
                json.dumps(preflight['receipt_sha256'], sort_keys=True,
                           separators=(',', ':')).encode('utf-8')).hexdigest(),
            staged_runner_sha256=evaluation.sha(__file__),
            postseal_preflight_sha256=evaluation.sha(postseal_preflight.__file__),
        )
        _write_json(stage / 'PROVENANCE.json', provenance)
        _verify_stage(stage, summary, metrics)
        _require(evaluation.sha(stage / 'protocol.json') == report.NUMERICAL_SHA,
                 'staged numerical protocol differs')
        _require(_read_json(stage / 'evaluation_protocol.json') == frozen_evaluation,
                 'staged evaluation protocol differs')
        integrity = {name: evaluation.sha(stage / name) for name in ARTIFACTS}
        _write_json(stage / 'REPORT_INTEGRITY.json', integrity)
        _require(_read_json(stage / 'REPORT_INTEGRITY.json') ==
                 {name: evaluation.sha(stage / name) for name in ARTIFACTS},
                 'report integrity differs')
        _rename_noreplace(stage, destination)
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    print(run())
