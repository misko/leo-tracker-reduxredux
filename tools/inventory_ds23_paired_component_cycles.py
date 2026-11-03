"""Find two simultaneous common components using native RF acquisition only."""

from itertools import combinations
from pathlib import Path
import json

import numpy as np

from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_paired_component_cycles'
AUTHORITY = ROOT/'reports/2026_10_21_ds23_differential_frame_phase_v2/protocol.json'
FS = 2500000.
PERIOD = 1/4.4e-6


def wrap(value, period):
    return (value+period/2) % period-period/2


def paired_cycles(first, second, *, minimum_margin=.3):
    """Do not reuse a native peak or collapse the two distinct RF components."""
    if not np.isfinite(minimum_margin) or minimum_margin <= 0:
        raise ValueError('positive finite native margin required')
    candidates = [[(k, p) for k, p in enumerate(peaks)
        if p['passed_fractional_margin_gate'] and p['fractional_margin'] >= minimum_margin]
        for peaks in [first, second]]
    pairs = []
    for i, a in candidates[0]:
        for j, b in candidates[1]:
            epochs = [p['integer_epoch_sample']+p['fractional_epoch_offset_samples'] for p in [a, b]]
            difference = abs(wrap(epochs[0]-epochs[1], FS/750))
            if difference <= .25:
                pairs.append(dict(indices=[i, j], peaks=[a, b], epochs=epochs,
                    native_epoch_difference_samples=float(difference),
                    minimum_native_margin=min(a['fractional_margin'], b['fractional_margin'])))
    result = []
    for a, b in combinations(pairs, 2):
        if any(i == j for i, j in zip(a['indices'], b['indices'], strict=True)):
            continue
        epoch_separation = [abs(wrap(a['epochs'][rx]-b['epochs'][rx], FS/750)) for rx in [0, 1]]
        frequency_separation = [abs(wrap(a['peaks'][rx]['fractional_tracking_cfo_hz']
            - b['peaks'][rx]['fractional_tracking_cfo_hz'], PERIOD)) for rx in [0, 1]]
        if min(epoch_separation) <= 10 or min(frequency_separation) <= 1500:
            continue
        result.append(dict(components=[a, b], epoch_separation_samples=epoch_separation,
            alias_aware_CFO_separation_hz=frequency_separation,
            minimum_native_margin=min(a['minimum_native_margin'], b['minimum_native_margin'])))
    return result


def main():
    OUT.mkdir(exist_ok=True)
    path = OUT/'inventory.json'
    if path.exists():
        raise FileExistsError('preserve prospective RF-only inventory')
    records = []
    authority = read(AUTHORITY)
    bindings = {}
    for filename, digest in authority['saved_panel_sha256'].items():
        panel = Path(filename)
        if sha(panel) != digest:
            raise ValueError('saved native dual-IQ panel changed')
        with np.load(panel, allow_pickle=False) as z:
            metadata = json.loads(str(z['metadata_json']))
        case = metadata['case']
        tracking = ROOT/'reports/2026_10_19_algo02_ds23_full'/case/'tracking.json'
        if not tracking.exists():
            continue
        doc = read(tracking)
        probes = {(r['visit_index'], r['receiver_id']):r for r in doc.get('source', doc)['probes']}
        bindings[str(tracking)] = sha(tracking)
        for point in metadata['points']:
            rx = [probes.get((point['visit_index'], r)) for r in [0, 1]]
            if any(r is None for r in rx):
                continue
            cycles = paired_cycles(rx[0]['candidates'], rx[1]['candidates'])
            if not cycles:
                continue
            best = max(cycles, key=lambda c:(c['minimum_native_margin'], min(c['epoch_separation_samples'])))
            records.append(dict(case=case, panel=str(panel), window_key=point['window_key'],
                visit_index=point['visit_index'], sample_counter=point['sample_counter'],
                channel=point['lane'][1], rf_hz=point['lane'][2], edge=point['edge'],
                sample_rate_hz=FS, raw_window_sha256=point['raw_window_sha256'], **best))
    selected = [max([r for r in records if r['case'] == case],
        key=lambda r:(r['minimum_native_margin'], -r['visit_index']))
        for case in sorted({r['case'] for r in records})]
    write(path, dict(selected=selected, available_cycles=len(records),
        panel_sha256=authority['saved_panel_sha256'], tracking_sha256=bindings,
        source_sha256=sha(Path(__file__)), authority_sha256=sha(AUTHORITY),
        selection='one strongest two-component window per scan; native minimum RF margin only',
        minimum_each_margin=.3, maximum_cross_RX_epoch_difference_samples=.25,
        minimum_component_epoch_separation_samples=10, minimum_alias_aware_CFO_separation_hz=1500,
        no_GPS_TLE_satellite_labels_complex_gain_outcomes_or_position_errors_used=True,
        no_new_RF_collection_or_raw_export=True,
        not_a_clock_measurement_until_component_cycles_and_ambiguity_and_covariance_are_validated=True))
    print(dict(scans=len(selected), windows=len(records), cases=[r['case'] for r in selected]), flush=True)


if __name__ == '__main__':
    main()
