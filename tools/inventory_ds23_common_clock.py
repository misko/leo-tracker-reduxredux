"""Freeze all native-qualified simultaneous-component windows, before fitting."""

from pathlib import Path
import json
import numpy as np

from inventory_ds23_paired_component_cycles import paired_cycles, AUTHORITY, FS
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_common_receiver_clock'
PREVIOUS = ROOT/'reports/2026_10_21_ds23_paired_component_cycles/inventory.json'


def main():
    OUT.mkdir(exist_ok=True)
    target = OUT/'inventory.json'
    if target.exists():
        raise FileExistsError('preserve the prospective native RF inventory')
    authority = read(AUTHORITY)
    old = read(PREVIOUS)
    engineering = {(r['case'], r['window_key']) for r in old['selected']}
    records = []
    bindings = {}
    for filename, digest in authority['saved_panel_sha256'].items():
        panel = Path(filename)
        assert sha(panel) == digest
        with np.load(panel, allow_pickle=False) as archive:
            metadata = json.loads(str(archive['metadata_json']))
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
            key = (case, point['window_key'])
            records.append(dict(case=case, panel=str(panel), window_key=point['window_key'],
                visit_index=point['visit_index'], sample_counter=point['sample_counter'],
                channel=point['lane'][1], rf_hz=point['lane'][2], edge=point['edge'],
                sample_rate_hz=FS, raw_window_sha256=point['raw_window_sha256'],
                cohort='engineering' if key in engineering else 'window_confirmation', **best))
    records.sort(key=lambda r:(r['case'], r['visit_index']))
    assert len(records) == old['available_cycles']
    assert sum(r['cohort'] == 'engineering' for r in records) == len(engineering)
    write(target, dict(selected=records, saved_panel_count=len(authority['saved_panel_sha256']),
        engineering_count=len(engineering), confirmation_count=len(records)-len(engineering),
        previous_inventory_sha256=sha(PREVIOUS), panel_sha256=authority['saved_panel_sha256'],
        tracking_sha256=bindings, source_sha256=sha(Path(__file__)),
        selected_using_only_native_RF_criteria_before_new_complex_clock_outcomes=True,
        confirmation_windows_are_not_new_scans_or_new_geographic_locations=True,
        no_new_RF_GPS_TLE_satellite_identity_or_position_error_used=True))
    print([(r['case'], r['window_key'], r['cohort']) for r in records], flush=True)


if __name__ == '__main__':
    main()
