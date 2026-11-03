"""Causal band-difference discovery using only public FAST evidence adapters."""
from pathlib import Path

import numpy as np


def metadata(document):
    """Bind hardware, UTC authority, and the recorded actual-RF hypothesis."""
    from leo.cli.shared_fast_position import load_input
    source = document['source']
    inputs = load_input(document)
    mapping = sorted(set((int(p['receiver_id']), int(p['channel']),
        str(p['edge']), float(p['actual_rf_hz'])) for p in source['probes']))
    return dict(first_sample_utc_ns=int(inputs.timing.first_sample_estimate_utc_ns),
        capture_end_utc_ns=int(inputs.capture_end_utc_ns),
        radio_id=source['radio_id'], stream_generation=source['stream_generation'],
        sample_rate_hz=int(source['sample_rate_hz']), capture_mode=source['capture_mode'],
        input_manifest_sha256=source['input_manifest_sha256'],
        analysis_manifest_sha256=source['analysis_manifest_sha256'],
        raw_recording_authority_digest=source['raw_recording_authority_digest'],
        rf_mapping=[list(row) for row in mapping],
        rf_mapping_authorities=document.get('provenance', {}).get('rf_mapping_authorities', []),
        clock_authority='public load_input host-bracket/device-counter reconstruction')


def compatible(target, donor):
    # Generation is an acquisition identity, not a persistent hardware setting.
    # Bind both exact tokens, while matching their acquisition protocol family.
    family = lambda row: row['stream_generation'].rsplit('-', 1)[0]
    return (family(target) == family(donor) and all(target[key] == donor[key] for key in
        ('radio_id', 'sample_rate_hz', 'capture_mode', 'rf_mapping')))


def extract_band_difference(terminal, stages):
    """Extract only the selected donor's two physical offsets, never its position."""
    selected = terminal['selection']['source']
    if selected == 'B-all':
        key = f"B-{stages['source-selection']['B_index']}"
    else:
        key = selected + '-high'
    result = stages[key]['result']
    if not result['audit']['accepted']:
        raise ValueError('Rejected calibration donor stage')
    fit = result['fit']
    receivers = [int(rx) for rx in fit['group_receivers']]
    offsets = np.asarray(fit['group_offsets_hz'], float)
    if (offsets.shape != (len(receivers),) or not np.isfinite(offsets).all()
            or set(receivers) != {0, 1}):
        raise ValueError('Two finite physical receiver band differences required')
    binding = next(row for row in terminal['stage_receipts'] if Path(row['path']).stem == key)
    return dict(receivers=receivers, offsets_hz=offsets.tolist(),
        selected_source=selected, calibration_stage=key,
        calibration_stage_sha256=binding['sha256'],
        donor_stage_stationarity=float(result['audit']['stationarity']))


def select_donor(target, candidates):
    """Most recent acquisition, with a conservative proven completion upper bound."""
    start = target['metadata']['first_sample_utc_ns']
    eligible = [row for row in candidates
        if row['job_id'] != target['job_id']
        and row['completion_upper_bound_utc_ns'] < start
        and row['metadata']['capture_end_utc_ns'] < start
        and compatible(target['metadata'], row['metadata'])]
    eligible.sort(key=lambda row: (-row['metadata']['first_sample_utc_ns'], row['job_id']))
    if not eligible:
        return dict(available=False, target=target,
            reason='No completed-before-target donor with identical hardware/rate/actual-RF mapping and stream family')
    selected = eligible[0]
    return dict(available=True, target=target, donor=selected,
        acquisition_age_s=(start-selected['metadata']['first_sample_utc_ns'])/1e9,
        completion_margin_s=(start-selected['completion_upper_bound_utc_ns'])/1e9,
        compatible_prior_candidates=len(eligible),
        exact_generation_prior_candidates=sum(row['metadata']['stream_generation']
            == target['metadata']['stream_generation'] for row in eligible),
        selected_generation_equal=selected['metadata']['stream_generation']
            == target['metadata']['stream_generation'],
        policy='nearest earlier acquisition; complete status before target start; identical hardware/rate/RF and stream family; generation tokens bound separately; band differences only')


def discover(store, sources):
    """Read all public input/status entries; never construct an archive path."""
    targets = []
    for source in sources:
        job, doc, terminal, _ = store.plot_evidence(source['job_id'])
        if (job['input_sha256'] != source['tracking_input_sha256']
                or job['terminal']['sha256'] != source['terminal_sha256']):
            raise ValueError('Frozen target input/terminal receipt differs')
        targets.append(dict(source_id=source['source_id'], job_id=job['job_id'],
            run_id=job['run_id'], input_sha256=job['input_sha256'],
            terminal_sha256=job['terminal']['sha256'], metadata=metadata(doc)))
    latest = max(row['metadata']['first_sample_utc_ns'] for row in targets)
    candidates, rejected = [], []
    input_count = 0
    for row in store.inputs():
        input_count += 1
        status = store.status(row['job_id'])
        if not status or status['state'] != 'complete' or status['updated_utc_ns'] >= latest:
            continue
        job, doc, terminal, stages = store.plot_evidence(row['job_id'])
        meta = metadata(doc)
        try:
            band = extract_band_difference(terminal, stages)
        except (KeyError, StopIteration, ValueError) as error:
            rejected.append(dict(job_id=job['job_id'], reason=str(error)))
            continue
        candidates.append(dict(job_id=job['job_id'], run_id=job['run_id'],
            input_sha256=job['input_sha256'], terminal_sha256=job['terminal']['sha256'],
            completion_upper_bound_utc_ns=int(job['updated_utc_ns']), metadata=meta,
            tle_sha256=terminal['provenance']['tle_sha256'],
            tle_collected_utc_ns=terminal['provenance']['tle_collected_utc_ns'],
            band=band))
    return dict(public_input_count=input_count, completed_prior_candidates=len(candidates),
        rejected_calibration_stages=rejected,
        sources=[select_donor(target, candidates) for target in targets],
        caveat='Status update is a conservative completion upper bound; later plot updates can exclude a result that was actually available earlier. RF mappings remain recorded hypotheses. No position or donor satellite identity is transported.')
