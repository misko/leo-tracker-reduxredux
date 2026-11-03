"""Adapter checks run in the selected Standard worker environment."""
import copy

import pytest

from tools.fast_scan_standard_pipeline import load_tracking_input


def document(rate):
    epoch = 1_700_000_000_000_000_000
    monotonic = 1_000_000_000
    return {
        'source': {
            'session_id': 'native-adapter-test', 'capture_mode': 'adaptive',
            'sample_rate_hz': rate, 'radio_id': 'synthetic', 'stream_generation': 'test',
            'input_manifest_sha256': 'sha256:' + '1' * 64,
            'analysis_manifest_sha256': 'sha256:' + '2' * 64,
            'raw_recording_authority_digest': 'sha256:' + '3' * 64,
            'qualified': True, 'timing': None,
            'probes': [dict(visit_index=0, receiver_id=0, probe_index=0, probe_start_ms=0,
                           channel=1, edge='upper', actual_rf_hz=10e9,
                           valid_start_counter=100, payload_start_sample=0, candidates=[])],
        },
        'clock_anchor': {
            'sample_counter': 100,
            'before': dict(realtime_ns=epoch, monotonic_ns=monotonic),
            'after': dict(realtime_ns=epoch + 1_000_000, monotonic_ns=monotonic + 1_000_000),
        },
        'delivery_clocks': [dict(realtime_ns=epoch + 1_000_000_000,
                                 monotonic_ns=monotonic + 1_000_000_000)],
        'last_sample_counter': 100 + rate,
    }


@pytest.mark.parametrize('rate,schema', [(2_500_000, 1), (10_000_000, 2)])
def test_native_and_legacy_timing_preserve_rate_counters_and_elapsed_time(rate, schema):
    value = document(rate)
    before = copy.deepcopy(value)
    source = load_tracking_input(value)
    assert source.sample_rate_hz == source.timing.sample_rate_hz == rate
    assert source.timing.schema_version == schema
    assert source.capture_end_utc_ns - source.capture_start_utc_ns == 1_000_000_000
    assert source.probes[0].valid_start_counter == 100
    assert source.probes[0].payload_start_sample == 0
    assert source.timing.qualified
    assert value == before


def test_native_timing_rejects_clock_steps_and_uncovered_counter():
    value = document(10_000_000)
    value['delivery_clocks'][0]['realtime_ns'] += 3_000_000_000
    with pytest.raises(ValueError, match='clock step'):
        load_tracking_input(value)
    value = document(10_000_000)
    value['clock_anchor']['sample_counter'] = 101
    with pytest.raises(ValueError, match='does not cover'):
        load_tracking_input(value)
