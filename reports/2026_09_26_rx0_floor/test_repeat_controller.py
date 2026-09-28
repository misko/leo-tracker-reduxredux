import importlib.util
import json
from pathlib import Path

import zstandard


def load_controller():
    spec = importlib.util.spec_from_file_location('controller', Path(__file__).with_name('repeat_controller.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_completed_analysis_and_strong_passes_count(tmp_path):
    controller = load_controller()
    controller.ROOT = tmp_path
    assert controller.strong_probe_counts('scan-test') is None
    directory = tmp_path / 'scanner-adaptive-analysis' / 'scan-test' / 'binding'
    directory.mkdir(parents=True)
    probes = [
        {'receiver_id': 0, 'candidates': [
            {'passed_fractional_margin_gate': True, 'fractional_margin': .2},
            {'passed_fractional_margin_gate': True, 'fractional_margin': .3},
        ]},
        {'receiver_id': 1, 'candidates': [
            {'passed_fractional_margin_gate': True, 'fractional_margin': .026},
            {'passed_fractional_margin_gate': False, 'fractional_margin': .2},
        ]},
    ]
    raw = json.dumps({'document': {'probes': probes}}).encode()
    (directory / 'visit.zst').write_bytes(zstandard.ZstdCompressor().compress(raw))
    assert controller.strong_probe_counts('scan-test') is None
    (directory / 'metrics-manifest.v8.json').write_text(json.dumps({'document': {'visits': [
        {'relative_path': 'visit.zst', 'uncompressed_bytes': len(raw)},
    ]}}))
    assert controller.strong_probe_counts('scan-test') == [1, 0]
