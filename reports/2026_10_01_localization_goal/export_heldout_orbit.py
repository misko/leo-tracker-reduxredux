"""Export one causal DS12 orbit bank using the pinned production public reader.

Run as the authorized reader user. Outputs belong to this experiment's /tmp
prefix; no archive or recording paths are modified. Input selection uses the
observation export's raw snapshot digest, never a production position result.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from leo.operations.tle_archive import TleArchiveReader

HERE = Path(__file__).resolve().parent


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output-prefix', type=Path, required=True)
    args = parser.parse_args()
    selection_path = HERE/'ds12-heldout-selection.json'
    assert digest(selection_path) == selection_path.with_suffix('.sha256').read_text().strip()
    selection = json.loads(selection_path.read_text())
    unit = next(r for r in selection['units'] if r['unit_id'] == args.unit)
    observations_path = HERE/'held-out'/args.unit/'observations.json'
    observations = json.loads(observations_path.read_text())
    receipt = json.loads((observations_path.parent/'export-receipt.json').read_text())
    assert digest(observations_path) == receipt['source_export_sha256']
    assert observations['session_id'] == unit['session_id']
    assert observations['manifest_sha256'] == unit['manifest_sha256']
    state_path = args.output_prefix.with_suffix('.npz')
    metadata_path = args.output_prefix.with_suffix('.json')
    extended_path = args.output_prefix.with_name(args.output_prefix.name+'-extended.npz')
    extended_metadata_path = args.output_prefix.with_name(args.output_prefix.name+'-extended.json')
    for path in [state_path, metadata_path, extended_path, extended_metadata_path]:
        if path.exists():
            raise FileExistsError(path)
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    candidates = [r for r in archive.list_snapshots()
                  if r.digest == observations['snapshot_sha256']
                  and r.collected_utc_ns < observations['start_utc_ns']]
    if not candidates:
        raise ValueError('no causal archive snapshot matches raw observation export')
    snapshot = max(candidates, key=lambda r: r.collected_utc_ns)
    adapter_path = HERE.parent/'2026_09_30_gaussian_sum_single_scan/evidence.py'
    adapter = load_module('heldout_orbit_export_adapter', adapter_path)
    meta = adapter.export_orbit_states(observations_path, snapshot.path, state_path)
    assert meta['tle']['causal'] and meta['tle']['sha256'] == observations['snapshot_sha256']
    meta['exporter_sha256'] = digest(__file__)
    meta['orbit_adapter_sha256'] = digest(adapter_path)
    with metadata_path.open('x') as stream:
        json.dump(meta, stream, indent=2, allow_nan=False)
    extension_path = HERE.parent/'2026_10_01_fixed_height_greedy/extend_orbits.py'
    extension = load_module('heldout_orbit_extension', extension_path)
    expanded = extension.extend_orbit_bank(
        observations_path, metadata_path, state_path, extended_path, padding_s=120.)
    with extended_metadata_path.open('x') as stream:
        json.dump(expanded, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(unit=args.unit, propagated_count=meta['propagated_count'],
                          rejected_count=meta['propagation_rejected_count'],
                          raw_snapshot_sha256=snapshot.digest,
                          extended_state_sha256=digest(extended_path))))


if __name__ == '__main__':
    main()
