"""Three user-authorized RX-only 300-second recordings, stop on any failure."""
import dataclasses
import hashlib
import json
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import leo.acquisition.continuous_window_ppu as provider
import leo.scanner.continuous_recording as recorder
from leo.acquisition.continuous_window_ppu import PpuContinuousWindowSource
from leo.acquisition.starlink_tuning import (
    STARLINK_LNB_LO_HZ,
    starlink_edge_rf_center_frequency_hz,
)
from leo.scanner.continuous_recording import run_continuous_recording
from leo.scanner.continuous_window import ContinuousWindowConfiguration
from leo.scanner.short_window import RfMappingAuthority, ShortWindowTarget
from leo.scanner.short_window_recording import json_metadata
from leo.storage.continuous_window import ContinuousWindowWriter, run_path

ROOT = Path('/srv/bulk/leo/fast8-radio20-20261009')
DATA = Path('/srv/postgres-nvme/fast8-radio20-20261009')
SERIAL = '1040005e0b100007100010000bf33a5d4d'
FREQUENCIES = (959687498,1190312500,1209687498,1440312500,
               1459687498,1690312496,1709687500,1940312500)

def emit(value):
    print(json.dumps({'utc': datetime.now(UTC).isoformat(), **value}), flush=True)

def write_exact(write, read, target):
    offsets = [0] + [offset for step in range(1, 17) for offset in (-step, step)]
    for offset in offsets:
        write(target + offset)
        observed = round(read())
        if observed == target:
            return
    raise RuntimeError(f'Cannot obtain exact LO readback {target}; observed {observed}')

def exact_radio_factory(uri, serial):
    from pluto_plus.hardware.preflight import verify_metadata_runtime
    verify_metadata_runtime(3)
    from pluto_plus.hardware.iio import IioRadioDevice
    from pluto_plus.setup_profiles import AD9361_2R2T_TARGET_PROFILE

    class ExactRadio(IioRadioDevice):
        def write_center_frequency_bufferless(self, frequency):
            write_exact(super().write_center_frequency_bufferless,
                        self.read_center_frequency, round(frequency))

    radio = ExactRadio(uri, serial=serial, radio_id=serial,
        expected_metadata_abi=3, require_idle_tandem_owner=True)
    radio.configure_rx_layout(AD9361_2R2T_TARGET_PROFILE.rx_layout_expectation)
    return radio

def measured_targets(edge):
    from pluto_plus.hardware.preflight import verify_metadata_runtime
    verify_metadata_runtime(3)
    from pluto_plus.hardware.iio import IioRadioDevice
    from pluto_plus.radio_lock import acquire_radio_lock
    from pluto_plus.setup_profiles import AD9361_2R2T_TARGET_PROFILE

    targets = []
    readbacks = []
    with acquire_radio_lock(SERIAL):
        radio = IioRadioDevice('ip:192.168.1.20', serial=SERIAL, radio_id=SERIAL,
            expected_metadata_abi=3, require_idle_tandem_owner=True)
        radio.configure_rx_layout(AD9361_2R2T_TARGET_PROFILE.rx_layout_expectation)
        radio.open()
        original = radio.read_receiver_settings_readback()
        try:
            assert radio.identity.serial == SERIAL
            assert radio.read_active_rx_fastlock_profile() is None
            radio.configure_adaptive_scan_geometry(sample_rate_hz=2500000,
                rf_bandwidth_hz=2500000, manual_gain_db=40, rx_mask=3)
            for channel in range(1, 9):
                nominal_rf = starlink_edge_rf_center_frequency_hz(channel, edge)
                nominal_if = nominal_rf - STARLINK_LNB_LO_HZ
                requested = nominal_if
                for _ in range(5):
                    radio.write_center_frequency_bufferless(requested)
                    observed = round(radio.read_center_frequency())
                    assert abs(observed - nominal_if) <= 10
                    if observed == requested:
                        break
                    requested = observed
                else:
                    raise RuntimeError('LO readback did not stabilize within bounded preparation')
                targets.append(ShortWindowTarget(
                    f'ch{channel}-{edge}', observed,
                    rf_center_hz=observed + STARLINK_LNB_LO_HZ,
                    lnb_lo_hz=STARLINK_LNB_LO_HZ, channel=channel, edge=edge,
                    rf_mapping_authority=RfMappingAuthority.HYPOTHESIS))
                readbacks.append({'channel': channel, 'edge': edge,
                    'nominal_rf_hz': nominal_rf, 'nominal_if_hz': nominal_if,
                    'applied_if_hz': observed, 'offset_hz': observed - nominal_if})
        finally:
            try:
                restored = radio.restore_receiver_settings_readback(original)
                (ROOT / f'{edge}-tuning-restoration.json').write_text(json.dumps(
                    json_metadata(dataclasses.asdict(restored)), indent=2) + '\n')
            finally:
                radio.close()
    (ROOT / f'{edge}-tuning-readbacks.json').write_text(
        json.dumps(readbacks, indent=2) + '\n')
    return targets

def main():
    assert json.loads((ROOT / 'deployment-result.json').read_text())['outcome'] == 'success'
    assert shutil.disk_usage(DATA).free > 12_000_000_000
    provenance = {
        'requested_runs': 2, 'requested_seconds_per_run': 300,
        'user_steering': 'Run 2 lower CH1-8, run 3 upper CH1-8; retain mixed run 1.',
        'iq_output_root': str(DATA),
        'retry_reason': 'Bulk and NVMe writer stalls exceeded 32-window queue; use 1024 windows.',
        'queue_windows': 1024, 'queue_bytes': 409600000,
        'serial': SERIAL, 'host': '192.168.1.20',
        'firmware': 'v0.62-plutoplus-spf-continuous-fast-scan',
        'frequency_plan_source': 'leo.acquisition.starlink_tuning',
        'frequency_semantics': (
            'All CH1-8, one edge per run, 9.75 GHz LNB LO hypothesis; '
            'LNB polarization and CH5-8 passband coverage not established.'),
        'source_files': {}, 'rf_transmit_enabled': False,
        'power_note': 'Uncalibrated -38 dBFS threshold; energy decisions do not identify Starlink.',
    }
    for module in (recorder, provider):
        p = Path(module.__file__)
        provenance['source_files'][str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    (ROOT / 'edge-recording-plan.json').write_text(json.dumps(provenance, indent=2) + '\n')
    results = []
    for number, edge in ((2, 'lower'), (3, 'upper')):
        targets = measured_targets(edge)
        configuration = ContinuousWindowConfiguration(targets=tuple(targets),
            gain_db=40, transition_budget_ms=20)
        run_id = f'fast8-r20-{edge}-ch1-8-exact-300s'
        path = run_path(DATA, run_id)
        path.mkdir(exist_ok=False)
        (path / 'requested-configuration.json').write_text(
            json.dumps(dataclasses.asdict(configuration), indent=2) + '\n')
        source = PpuContinuousWindowSource('192.168.1.20', expected_serial=SERIAL,
                                          radio_factory=exact_radio_factory)
        sink = ContinuousWindowWriter(path, run_id, configuration,
            radio={'provider': 'ppu-continuous-v5', 'serial': SERIAL,
                   'host': '192.168.1.20', 'firmware': provenance['firmware']})
        power_counts = Counter()
        quality_counts = Counter()
        timing = {'last_report': 0.0}
        started_utc = datetime.now(UTC).isoformat()
        def progress(record, number=number, sink=sink, power_counts=power_counts,
                     quality_counts=quality_counts, timing=timing):
            state = record['state']
            if state == 'capture_complete':
                for p in record['powers']:
                    power_counts[p['decision']] += 1
                quality_counts.update(record['acquisition']['quality_flags'])
                if time.monotonic() - timing['last_report'] >= 30:
                    timing['last_report'] = time.monotonic()
                    emit({'run': number, 'state': state,
                          'captured_windows': record['captured_windows'],
                          'durable_windows': sink.durable_windows,
                          'power_decisions': dict(power_counts),
                          'quality_flags': dict(quality_counts)})
            elif state in ('running', 'stop_requested'):
                emit({'run': number, **record})
        emit({'run': number, 'state': 'preparing', 'path': str(path)})
        started = time.monotonic()
        result = run_continuous_recording(source, configuration, sink,
            stop_after_seconds=300, on_progress=progress,
            queue_windows=1024, queue_bytes=409600000,
            shutdown_timeout_seconds=60)
        document = {
            'kind': 'continuous_rx_antenna_recording', 'requested_seconds': 300,
            'started_utc': started_utc, 'finished_utc': datetime.now(UTC).isoformat(),
            'wall_seconds_including_setup_and_restore': time.monotonic() - started,
            'recording': json_metadata(dataclasses.asdict(result)),
            'power_decisions': dict(power_counts), 'quality_flags': dict(quality_counts),
            'qualified_tracking': False,
        }
        (path / 'qualification.json').write_text(json.dumps(document, indent=2) + '\n')
        results.append({'run': number, 'path': str(path), **document})
        (ROOT / 'edge-recording-results.json').write_text(json.dumps(results, indent=2) + '\n')
        emit({'run': number, 'state': 'finished', **document})
        if (result.fault or result.written_windows != result.captured_windows
                or result.terminal is None):
            raise RuntimeError('Recording failed; retained evidence, remaining runs not started')
        if result.terminal.state.name != 'COMPLETED' or result.terminal.error:
            raise RuntimeError('Device terminal failed; do not start another recording')

if __name__ == '__main__':
    main()
