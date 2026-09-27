"""Proposal-coordinate audit; never interprets a proposal as a detection."""
import math


def injected_pilots(case):
    """Read only the frozen construction recipe, independently of outcomes."""
    return [
        {'trajectory_id': component.get('trajectory_id', str(index)),
         'epoch_samples': case['epoch_relative_samples']
         + component.get('epoch_offset_samples', 0.0),
         'cfo_hz': component['cfo_hz']}
        for index, component in enumerate(case['components'])
        if component['type'] == 'pilot'
    ]


def coordinate_error(candidate, truth, rate):
    values = (candidate['epoch_samples'], candidate['cfo_hz'],
              truth['epoch_samples'], truth['cfo_hz'])
    if not all(math.isfinite(value) for value in values):
        raise ValueError('nonfinite proposal or truth')
    window = candidate['window']
    if type(window) is not int or not 0 <= window < 6:
        raise ValueError('proposal outside recorded windows')
    period = rate / 750.0
    delta = window * (rate // 50) + candidate['epoch_samples'] - truth['epoch_samples']
    timing_us = abs((delta + period / 2) % period - period / 2) / rate * 1e6
    cfo_hz = abs(candidate['cfo_hz'] - truth['cfo_hz'])
    return {'timing_error_us': timing_us, 'cfo_error_hz': cfo_hz,
            'coordinate_match': timing_us <= 2.0 and cfo_hz <= 8000.0}


def score_case(case, candidates):
    rate = case['rate_hz']
    if rate not in (2_500_000, 5_000_000):
        raise ValueError('unsupported geometry')
    truths = injected_pilots(case)
    comparisons = [
        {'proposal_index': index, 'trajectory_id': truth['trajectory_id'],
         'supported': bool(candidate['supported']),
         **coordinate_error(candidate, truth, rate)}
        for index, candidate in enumerate(candidates) for truth in truths
    ]
    return {
        'pilot_truth_count': len(truths),
        'proposal_count': len(candidates),
        'supported_proposal_count': sum(bool(c['supported']) for c in candidates),
        'any_coordinate_match': (
            any(c['coordinate_match'] for c in comparisons) if truths else None),
        'any_supported_coordinate_match': (
            any(c['coordinate_match'] and c['supported'] for c in comparisons)
            if truths else None),
        'each_injected_pilot_supported': {
            truth['trajectory_id']: any(
                c['trajectory_id'] == truth['trajectory_id']
                and c['coordinate_match'] and c['supported'] for c in comparisons)
            for truth in truths},
        'comparisons': comparisons,
        'detector_decision': None,
        'false_alarm_rate_estimate': None,
    }
