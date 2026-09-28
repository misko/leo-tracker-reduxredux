"""Alternating original/current full Standard numerical analysis on saved 2.5-MS/s visits."""
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import signal
import sys
import time
from unittest.mock import patch

import numpy as np
from pydantic import TypeAdapter
import leo.scanner.detector as detector
import leo.analysis.starlink.pilot_methods as current_pilot
import leo.analysis.starlink.acquisition as current_acquisition
from leo.scanner.models import ScannerConfiguration, current_low_band_targets
from leo.scanner.ports import ScanRadioIdentity
from leo.scanner.standard_analysis import ScannerAnalysisFrameInput, SegmentedScannerSource, analyze_standard_scanner
from compare import differences

HERE = Path(__file__).resolve().parent


def load(name, path):
    name = 'leo.analysis.starlink._paired_' + name
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run():
    signal.alarm(300)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    output = HERE/'paired-full.json'
    if output.exists():
        raise ValueError('output already exists')
    old_pilot = load('pilot', HERE/'pilot_methods_baseline.py')
    old_acquisition = load('acquisition', HERE/'acquisition_peak/original/acquisition.py')
    variants = {'baseline': (old_pilot, old_acquisition),
                'candidate': (current_pilot, current_acquisition)}
    result = {'affinity': sorted(os.sched_getaffinity(0)), 'repetitions': 3,
              'scope': 'full Standard numerical analysis; resident IQ; excludes PNG, archive decompression and publication',
              'hashes': {k: [hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in v]
                         for k, v in variants.items()}, 'cases': []}
    base = Path('/tmp/leo-static-arm15-20260927-v3')
    manifest = json.loads((base/'manifest.json').read_text())
    for index in (24, 25, 27, 40, 41):
        case = manifest['cases'][index]
        raw = (base/'data'/case['raw_file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case['raw_sha256']
        iq = np.frombuffer(raw, dtype='<i2').reshape(-1, 2, 2)
        target = next(t for t in current_low_band_targets() if t.channel == case['channel'] and t.edge == case['edge'])
        config = ScannerConfiguration(targets=(target,))
        source = SegmentedScannerSource('saved-benchmark', 'file://'+case['raw_file'],
            'sha256:'+case['raw_sha256'], ScanRadioIdentity('saved', 'saved', 'saved'), config,
            (ScannerAnalysisFrameInput(0, target, 0, target.if_center_hz, target.if_center_hz, None, None, iq),))
        measurements = []; expected = None; exact = True
        for repeat in range(4):
            order = ('baseline', 'candidate') if repeat % 2 == 0 else ('candidate', 'baseline')
            for name in order:
                pilot, acquisition = variants[name]
                with patch.object(detector, 'acquire_symbolwise', acquisition.acquire_symbolwise), \
                     patch.object(detector, 'conditioned_glrt64_score', pilot.conditioned_glrt64_score):
                    cpu = time.process_time(); wall = time.perf_counter()
                    got = analyze_standard_scanner(source)
                    cpu = time.process_time()-cpu; wall = time.perf_counter()-wall
                document = TypeAdapter(type(got)).dump_python(got, mode='json')
                document['report'].pop('analysis_elapsed_ms')
                if expected is None:
                    expected = document
                errors = differences(expected, document)
                if errors:
                    raise ValueError(errors[:10])
                exact &= expected == document
                if repeat:
                    measurements.append({'variant': name, 'repeat': repeat, 'cpu_s': cpu, 'wall_s': wall})
        result['cases'].append({'case_id': case['case_id'], 'raw_sha256': case['raw_sha256'],
              'configuration': config.model_dump(mode='json'), 'exact_output_equal': exact,
              'measurements': measurements, 'scientific_output': expected})
        output.write_text(json.dumps(result, indent=2)+'\n')
        print(case['case_id'], exact, measurements, flush=True)
    result['complete'] = True
    output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    run()
