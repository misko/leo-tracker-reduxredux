"""Metadata-only arrival-epoch inventory; no new peak or identity selection."""
from pathlib import Path
import math
import sys
import numpy as np

PHASE_SOURCE = Path(__file__).resolve().parents[1]/'frame_phase_audit'
sys.path.insert(0, str(PHASE_SOURCE))
from phase_math import relative_counter, arrival_phase_samples, first_frame_time_s


def group_id(source, probe):
    from leo.contracts.digests import canonical_digest
    return canonical_digest(dict(capture=source.input_manifest_sha256, visit=probe.visit_index,
        rx=probe.receiver_id, probe=probe.probe_index))


def original_winners(projected):
    """Replay the declared original highest-margin export, no CFO/phase choice."""
    result = {}
    for point in projected:
        previous = result.get(point.source_group_id)
        if previous is None or (-point.margin, point.candidate_rank, point.candidate_id) < (
            -previous.margin, previous.candidate_rank, previous.candidate_id):
            result[point.source_group_id] = point
    return result


def probe_epochs(source, probe):
    fs = source.sample_rate_hz
    if source.timing is None:
        return dict(available=False, reason='missing_public_timing_authority', candidates=[])
    counter = relative_counter(probe.valid_start_counter, source.timing.session_start_device_sample_counter,
        probe.probe_start_ms, fs)
    candidates = []
    for c in probe.candidates:
        offset = c.fractional_epoch_offset_samples
        valid = (isinstance(c.integer_epoch_sample, (int, np.integer)) and not isinstance(c.integer_epoch_sample, bool)
            and offset is not None and math.isfinite(offset))
        row = dict(candidate_rank=int(c.candidate_rank), integer_epoch_sample=c.integer_epoch_sample,
            fractional_epoch_offset_samples=offset, passed_fractional_margin_gate=bool(c.passed_fractional_margin_gate),
            fractional_margin=float(c.fractional_margin), phase_available=bool(valid))
        if valid:
            integer = counter+int(c.integer_epoch_sample)
            row.update(positive_arrival_phase_samples=arrival_phase_samples(counter, c.integer_epoch_sample, offset, fs),
                first_frame_session_relative_s=first_frame_time_s(counter, c.integer_epoch_sample, offset, fs),
                first_frame_session_relative_integer_sample=integer,
                first_frame_device_integer_counter=int(source.timing.session_start_device_sample_counter)+integer,
                first_frame_fractional_sample=offset,
                first_frame_estimate_utc_ns=int(source.timing.first_sample_estimate_utc_ns)+round((integer+offset)*1e9/fs))
        else:
            row['reason'] = 'missing_or_invalid_fractional_anchor_no_value_reconstructed'
        candidates.append(row)
    valid = [r for r in candidates if r['phase_available']]
    passed = [r for r in valid if r['passed_fractional_margin_gate']]
    def counts(rows):
        phases = sorted(set(r['positive_arrival_phase_samples'] for r in rows))
        distances = [abs((a-b+fs/750/2)%(fs/750)-fs/750/2)
            for i, a in enumerate(phases) for b in phases[i+1:]]
        return dict(candidate_count=len(rows), unique_integer_anchors=len(set(r['integer_epoch_sample'] for r in rows)),
            exact_unique_fractional_phases=len(phases),
            minimum_pairwise_circular_phase_separation_samples=float(min(distances)) if distances else None,
            maximum_pairwise_circular_phase_separation_samples=float(max(distances)) if distances else None)
    return dict(available=True, reason=None, relative_probe_counter=counter,
        valid_start_counter=int(probe.valid_start_counter), probe_start_ms=int(probe.probe_start_ms),
        public_retained_candidate_count=len(candidates), missing_fractional_candidate_count=len(candidates)-len(valid),
        all_available=counts(valid), passed_available=counts(passed), candidates=candidates)
