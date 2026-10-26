"""One unchanged original-window replay; no catalogue, fitting or RF capture."""
import hashlib
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent
TRACKING = Path('/srv/bulk/leo/research/ds25-20261024/DS24-0011/tracking.json')
TRACKING_SHA = 'a0b25c6abea7979f935ce2eaf8b289eb1831b206a6deca65854817e91c8a85f5'
CODE = 'sha256:124afbbc81870a4079b272bd828d4a99f716e54624a073d9cb13acc2a1b7fe16'
ENVIRONMENT = 'sha256:8ccb220369bccb42b7bea5dcd3bfa546e132d2250a674e6eac7388a2a425e3b9'
FIELDS = {
    'fractional_epoch_offset_samples': 1e-9,
    'fractional_tracking_cfo_hz': 1e-6,
    'fractional_exact_score': 1e-10,
    'fractional_control_score': 1e-10,
    'fractional_margin': 1e-10,
}
EXACT = ('candidate_rank', 'integer_epoch_sample', 'passed_fractional_margin_gate')


def compare_candidates(expected, actual):
    checks = [{'field': 'candidate_count', 'passed': len(expected) == len(actual)}]
    for i, (old, new) in enumerate(zip(expected, actual)):
        for field in EXACT:
            checks.append({'candidate_index': i, 'field': field,
                           'passed': old[field] == new[field]})
        for field, tolerance in FIELDS.items():
            delta = abs(float(old[field]) - float(new[field]))
            checks.append({'candidate_index': i, 'field': field,
                           'absolute_difference': delta if math.isfinite(delta) else None,
                           'tolerance': tolerance,
                           'passed': math.isfinite(delta) and delta <= tolerance})
    return {'all_passed': all(x['passed'] for x in checks), 'checks': checks}


def exported(receivers):
    rows = {}
    for receiver in receivers:
        candidates = []
        for c in receiver.candidates:
            if c.fractional_epoch_status != 'complete' or any(
                getattr(c, key) is None for key in FIELDS
            ):
                continue
            candidates.append({
                'candidate_rank': c.candidate_rank,
                'integer_epoch_sample': c.epoch_sample,
                **{field: getattr(c, field) for field in FIELDS},
                'passed_fractional_margin_gate': c.fractional_margin >= .025,
            })
        rows[receiver.receiver_id] = candidates
    return rows


def main():
    started = time.monotonic()
    from leo.contracts.fast_scan_native import parse_fast_policy
    from leo.processing.fast_scan import implementation_identity
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow, analyze_window
    from leo.storage.short_window import ShortWindowReader
    assert implementation_identity() == (CODE, ENVIRONMENT)
    authority = json.loads((ROOT / 'replay_authority.json').read_text())
    assert authority['matches_persisted_implementation'] and authority['matches_persisted_environment']
    metadata = json.loads((ROOT / 'replay_metadata.json').read_text())
    raw = TRACKING.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == TRACKING_SHA
    tracking = json.loads(raw)
    expected = {p['receiver_id']: p for p in tracking['source']['probes'] if p['visit_index'] == 0}
    assert set(expected) == {0, 1}
    reader = ShortWindowReader(Path(metadata['segment']['path']).parent)
    assert reader.manifest_sha256 == metadata['segment']['sha256']
    # Exhaustion is essential: it verifies all 64 window hashes and the entire
    # containing compressed/decompressed chunk, while returning only sequence0.
    selected = tuple(reader.windows(start_sequence=0, stop_sequence=1))
    assert len(selected) == 1
    selected = selected[0]
    index = selected.index.model_dump(mode='json')
    assert index == metadata['first_index']
    assert index['sequence'] == 0 and index['sample_count'] == 200000
    assert index['receiver_count'] == 2
    target = next(t for t in reader.manifest.configuration['targets']
                  if t['target_id'] == index['target_id'])
    window = VerifiedFastWindow(0, index['iq_sha256'], index['acquisition'],
                                target, selected.samples, 10000000)
    policy = parse_fast_policy(authority['execution']['pipeline_configuration']['stages']['fast-scan'])
    verified_s = time.monotonic() - started
    result = analyze_window(window, (0, 1), None, policy)
    actual = exported(result.receivers)
    assert result.status == 'processed'
    assert all(p['valid_start_counter'] == result.sample_start for p in expected.values())
    assert set(actual) == set(expected)
    comparisons = {str(rx): compare_candidates(expected[rx]['candidates'], actual[rx]) for rx in expected}
    output = {'case': 'DS24-0011', 'sequence': 0, 'global_visit': 0,
              'iq_sha256': index['iq_sha256'], 'sample_start': result.sample_start,
              'sample_rate_hz': 10000000, 'window_ms': 20,
              'receiver_ids': [0, 1], 'status': result.status,
              'verified_window_hashes_in_chunk': 64,
              'compressed_bytes_verified': reader.manifest.chunks[0].compressed_bytes,
              'uncompressed_bytes_verified': reader.manifest.chunks[0].uncompressed_bytes,
              'full_reader_exhausted': True, 'historical_implementation_and_environment_match': True,
              'code_digest': CODE, 'environment_digest': ENVIRONMENT,
              'tracking_path': str(TRACKING), 'tracking_sha256': TRACKING_SHA,
              'expected_probes': expected, 'actual_exported_candidates': actual,
              'full_window_result': result.model_dump(mode='json'),
              'comparisons': comparisons,
              'all_passed': all(c['all_passed'] for c in comparisons.values()),
              'metadata_and_chunk_verification_s': verified_s,
              'total_s': time.monotonic() - started,
              'new_RF': False, 'injection': False, 'position_fit': False,
              'noise_only_status_established': False}
    assert implementation_identity() == (CODE, ENVIRONMENT)
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
