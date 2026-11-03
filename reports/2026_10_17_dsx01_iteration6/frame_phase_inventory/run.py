"""Bound all15 frozen cohorts to source-probe candidates, no IQ or models."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from inventory import group_id, original_winners, probe_epochs, PHASE_SOURCE

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
DATA = REPORTS/'2026_10_16_dsx01_fast_association_losses'


def sha(path):
    return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False);stream.write('\n')


def main():
    from leo.storage.shared_fast_scan import SharedFastScanStore
    from leo.cli.shared_fast_position import load_input
    from leo.application.scanner_trajectory import project_scanner_candidates
    started = time.monotonic()
    with (DATA/'membership.csv').open() as stream:
        memberships = list(csv.DictReader(stream))
    frozen = [json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    frozen = {(r['source_id'], r['observation_id']):r for r in frozen}
    sources = json.loads((DATA/'sources.json').read_text())
    store = SharedFastScanStore('/srv/bulk/leo', 'shared-scan-q-v2')
    records, source_receipts = [], []
    for binding in sources:
        sid = binding['source_id']
        selected = [r for r in memberships if r['source_id'] == sid]
        job, document, terminal, _ = store.plot_evidence(binding['job_id'])
        assert job['input_sha256'] == binding['tracking_input_sha256']
        assert job['terminal']['sha256'] == binding['terminal_sha256']
        source = load_input(document)
        winners = original_winners(project_scanner_candidates(source))
        probes = {group_id(source, p):p for p in source.probes}
        assert len(probes) == len(source.probes)
        receipt = dict(source_id=sid, job_id=binding['job_id'], tracking_input_sha256=job['input_sha256'],
            terminal_sha256=job['terminal']['sha256'], input_manifest_sha256=source.input_manifest_sha256,
            analysis_manifest_sha256=source.analysis_manifest_sha256,
            raw_recording_authority_digest=source.raw_recording_authority_digest,
            radio_id=source.radio_id, stream_generation=source.stream_generation, session_id=source.session_id,
            capture_mode=source.capture_mode, qualified=source.qualified,
            sample_rate_hz=source.sample_rate_hz, physical_frame_period_samples=source.sample_rate_hz/750,
            frame_period_definition='Fs /750; positive arrival epoch modulo physical period',
            session_start_device_sample_counter=source.timing.session_start_device_sample_counter,
            first_sample_estimate_utc_ns=source.timing.first_sample_estimate_utc_ns,
            receiver_convention='public contract0/1; frozen human report RX1/RX2 = contract+1',
            timing_authority=source.timing.model_dump(mode='json'))
        source_receipts.append(receipt)
        for membership in selected:
            identity = membership['observation_id']
            row = dict(region_id=membership['region_id'], source_id=sid, observation_id=identity,
                source_tracking_input_sha256=job['input_sha256'],
                source_analysis_manifest_sha256=source.analysis_manifest_sha256,
                source_raw_recording_authority_digest=source.raw_recording_authority_digest)
            if identity not in probes or identity not in winners:
                row.update(available=False, reason='frozen_group_id_absent_from_public_probe_or_original_winner')
                records.append(row);continue
            reference = frozen[sid, identity]
            point, probe = winners[identity], probes[identity]
            assert point.visit_index == probe.visit_index and point.probe_index == probe.probe_index
            assert point.receiver_id == probe.receiver_id == reference['receiver']-1
            assert point.channel == probe.channel == reference['channel']
            assert point.actual_rf_hz == probe.actual_rf_hz == reference['actual_rf_hz']
            support_s = (point.support_center_utc_ns-source.timing.first_sample_estimate_utc_ns)/1e9
            assert support_s == reference['time_s']
            epochs = probe_epochs(source, probe)
            chosen = [r for r in epochs['candidates'] if r['candidate_rank'] == point.candidate_rank]
            if len(chosen) != 1: raise ValueError('Original winning candidate rank not unique in public probe')
            winner = chosen[0]
            row.update(available=bool(epochs['available'] and winner['phase_available']),
                reason=None if winner['phase_available'] else winner['reason'],
                visit_index=probe.visit_index, probe_index=probe.probe_index,
                receiver_contract=probe.receiver_id, receiver_report=probe.receiver_id+1, channel=probe.channel,
                actual_rf_hz=probe.actual_rf_hz, sample_rate_hz=source.sample_rate_hz,
                physical_period_samples=source.sample_rate_hz/750,
                cfo_support_center_session_relative_s=support_s,
                cfo_support_start_utc_ns=point.support_start_utc_ns,
                cfo_support_center_utc_ns=point.support_center_utc_ns,
                cfo_support_end_utc_ns=point.support_end_utc_ns,
                winner_candidate_rank=point.candidate_rank, winner=winner,
                probe_phase_inventory=epochs)
            if winner['phase_available']:
                row['support_center_minus_first_frame_s'] = support_s-winner['first_frame_session_relative_s']
            records.append(row)
    assert len(records) == len(memberships) == 693
    save(HERE/'source-provenance.json', source_receipts)
    with (HERE/'observations.jsonl').open('x') as stream:
        for row in records:stream.write(json.dumps(row, separators=(',', ':'), allow_nan=False)+'\n')
    regions = []
    for region in sorted({r['region_id'] for r in records}):
        rows = [r for r in records if r['region_id'] == region]
        available = [r for r in rows if r['available']]
        hist = lambda field:dict(sorted(Counter(str(r['probe_phase_inventory']['passed_available'][field]) for r in available).items()))
        regions.append(dict(region_id=region, source_id=rows[0]['source_id'], original_denominator=len(rows),
            available=len(available), missing=len(rows)-len(available),
            passed_candidate_count_histogram=hist('candidate_count'),
            passed_unique_integer_anchor_count_histogram=hist('unique_integer_anchors'),
            passed_exact_unique_fractional_phase_count_histogram=hist('exact_unique_fractional_phases'),
            observations_with_multiple_passed_fractional_phases=sum(r['probe_phase_inventory']['passed_available']['exact_unique_fractional_phases']>1 for r in available),
            winner_phase_range_samples=[min(r['winner']['positive_arrival_phase_samples'] for r in available), max(r['winner']['positive_arrival_phase_samples'] for r in available)] if available else None))
    save(HERE/'regions.json', regions)
    summary = dict(original_observations=693, original_windows=15,
        available=sum(r['available'] for r in records), unavailable=sum(not r['available'] for r in records),
        all_frozen_observation_ids_exactly_matched=all('winner_candidate_rank' in r for r in records),
        observations_with_multiple_passed_fractional_phases=sum(r['observations_with_multiple_passed_fractional_phases'] for r in regions),
        observations_with_multiple_passed_integer_anchors=sum(r['probe_phase_inventory']['passed_available']['unique_integer_anchors']>1 for r in records if r['available']),
        total_public_retained_candidates=sum(r['probe_phase_inventory']['public_retained_candidate_count'] for r in records if r['available']),
        total_passed_candidates=sum(r['probe_phase_inventory']['passed_available']['candidate_count'] for r in records if r['available']),
        total_missing_fractional_candidate_metadata=sum(r['probe_phase_inventory']['missing_fractional_candidate_count'] for r in records if r['available']),
        support_center_minus_first_frame_s=[min(r['support_center_minus_first_frame_s'] for r in records if r['available']), max(r['support_center_minus_first_frame_s'] for r in records if r['available'])],
        phase_units='samples; sample rate explicitly bound per source; positive arrival modulo Fs/750',
        exact_phase_count_qualification='Exact distinct stored phases, not distinct emitters. Subsample differences can reflect alternatives on one peak; all candidates and circular separations retained without clustering or choosing another peak.',
        winner_policy='Frozen original highest-margin passed candidate, ties candidate rank/ID; no CFO, phase, satellite or window fitting/selection.',
        elapsed_seconds=time.monotonic()-started,
        input_sha256={name:sha(DATA/name) for name in ['membership.csv', 'context-observations.jsonl', 'sources.json']},
        code_sha256={str(path):sha(path) for path in [HERE/'inventory.py', HERE/'run.py', PHASE_SOURCE/'phase_math.py']},
        qualification='Inventory only: no missing values reconstructed, no phase fit, unwrapping or geometric/physical model. Existing counter/sample-rate authority and candidate metadata bound, not proven transmitter epoch or satellite identity.')
    save(HERE/'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
