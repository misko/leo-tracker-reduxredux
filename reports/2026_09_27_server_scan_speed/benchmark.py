"""Bounded saved-IQ benchmark of the complete standard scanner probe schedule."""
import argparse
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import platform
import signal
import sys
import time
from unittest.mock import patch

import numpy as np
from pydantic import TypeAdapter
import leo.scanner.detector as detector
import leo.analysis.starlink.pilot_methods as pilot
import leo.analysis.starlink.acquisition as acquisition
from leo.analysis.starlink.acquisition import _folded_anchor_score_grid_backend
from leo.scanner.models import ScannerConfiguration, current_low_band_targets


def run():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--baseline-module', type=Path)
    p.add_argument('--baseline-acquisition', type=Path)
    p.add_argument('--full-analysis', action='store_true')
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--indices', type=int, nargs='+', default=[24, 56, 88, 96])
    a = p.parse_args()
    if not 1 <= a.repeats <= 5:
        raise ValueError('bounded repeats')
    signal.alarm(600)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    out = a.output
    out.mkdir(parents=True, exist_ok=False)
    module = pilot
    if a.baseline_module:
        name = 'leo.analysis.starlink._benchmark_baseline_pilot'
        spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(a.baseline_module)))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    base = Path('/tmp/leo-static-arm15-20260927-v3')
    manifest = json.loads((base / 'manifest.json').read_text())
    receipt = {'python': sys.version, 'platform': platform.platform(),
               'affinity': sorted(os.sched_getaffinity(0)),
               'backend': _folded_anchor_score_grid_backend(),
               'pilot_sha256': hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
               'scope': 'resident saved IQ; complete 11-probe dual-RX scanner; excludes archive decompression, waterfalls and publication',
               'cases': []}
    acquisition_module = acquisition
    if a.baseline_acquisition:
        name = 'leo.analysis.starlink._benchmark_baseline_acquisition'
        spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(a.baseline_acquisition)))
        acquisition_module = importlib.util.module_from_spec(spec)
        sys.modules[name] = acquisition_module
        spec.loader.exec_module(acquisition_module)
    acquire = acquisition_module.acquire_symbolwise
    receipt['acquisition_sha256'] = hashlib.sha256(Path(acquisition_module.__file__).read_bytes()).hexdigest()
    receipt['full_analysis'] = a.full_analysis
    for index in a.indices:
        case = manifest['cases'][index]
        raw_path = base / 'data' / case['raw_file']
        raw = raw_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case['raw_sha256']
        iq = np.frombuffer(raw, dtype='<i2').reshape(-1, 2, 2)
        values = iq[:, :, 0].astype(np.complex64) + 1j * iq[:, :, 1]
        config = ScannerConfiguration(sample_rate_hz=case['rate_hz'],
                   bandwidth_hz=case['rate_hz'], targets=current_low_band_targets())
        if a.full_analysis:
            from leo.scanner.standard_analysis import (ScannerAnalysisFrameInput,
                SegmentedScannerSource, analyze_standard_scanner)
            from leo.scanner.ports import ScanRadioIdentity
            target = next(t for t in config.targets if t.channel == case['channel'] and t.edge == case['edge'])
            config = config.model_copy(update={'targets': (target,)})
            source = SegmentedScannerSource('saved-benchmark', 'file://' + str(raw_path),
                'sha256:' + case['raw_sha256'], ScanRadioIdentity('saved', 'saved', 'saved'), config,
                (ScannerAnalysisFrameInput(0, target, 0, target.if_center_hz,
                    target.if_center_hz, None, None, iq),))
            receipt['scope'] = 'complete one-frame Standard numerical analysis including waterfalls and pilot Doppler; excludes archive decompression, PNG rendering and publication'
        rows = []
        result = None
        for repeat in range(a.repeats + 1):
            stages = {'acquisition_s': 0., 'glrt_s': 0., 'acquisition_calls': 0, 'glrt_calls': 0}
            def timed(key, function):
                def call(*args, **kwargs):
                    t = time.process_time()
                    try:
                        return function(*args, **kwargs)
                    finally:
                        stages[key + '_s'] += time.process_time() - t
                        stages[key + '_calls'] += 1
                return call
            t = time.perf_counter(); cpu = time.process_time()
            with patch.object(detector, 'acquire_symbolwise', timed('acquisition', acquire)), \
                 patch.object(detector, 'conditioned_glrt64_score', timed('glrt', module.conditioned_glrt64_score)):
                detected = (analyze_standard_scanner(source) if a.full_analysis else
                    detector.analyze_glrt64_dwell(values, config, edge=case['edge']))
                got = TypeAdapter(type(detected)).dump_python(detected, mode='json')
                if a.full_analysis:
                    got['report'].pop('analysis_elapsed_ms')
            elapsed = {'wall_s': time.perf_counter()-t, 'cpu_s': time.process_time()-cpu, **stages}
            if result is not None and got != result:
                raise ValueError('non-repeatable scanner result')
            result = got
            if repeat:
                rows.append(elapsed)
        item = {'case_id': case['case_id'], 'rate_hz': case['rate_hz'],
                'raw_sha256': case['raw_sha256'], 'configuration': config.model_dump(mode='json'),
                'measurements': rows, 'result': result}
        receipt['cases'].append(item)
        (out / 'results.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(case['rate_hz'], rows, flush=True)
    receipt['complete'] = True
    (out / 'results.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    run()
