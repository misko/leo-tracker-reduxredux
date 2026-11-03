"""Export immutable GLRT inputs through public read-only capture ports.

Run with the installed analysis-release interpreter, not a reference repository.
No satellite association or localization outcome is calculated by this stage.
"""
import argparse
import inspect
import json
import time
from pathlib import Path

from cohort import OUT, canonical, digest
from iq_visits import read_event, visit_ordinals


def export(scan, destination, cohort_hash, *, bulk_root=Path('/srv/bulk/leo')):
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris

    started = time.monotonic()
    sources = {str(Path(inspect.getfile(obj))): digest(Path(inspect.getfile(obj)).read_bytes())
               for obj in (project_scanner_candidates, ScannerTrackingInputStore, AdaptiveHopIqStore,
                           TleArchiveReader, parse_element_sets, exclude_labelled_starlink_debris)}
    sources[str(Path(__file__))] = digest(Path(__file__).read_bytes())
    sources[str(Path(inspect.getfile(read_event)))] = digest(Path(inspect.getfile(read_event)).read_bytes())
    signature = dict(cohort_sha256=cohort_hash, sources=sources, session_id=scan['session_id'],
                     manifest_sha256=scan['manifest_sha256'])
    if destination.exists():
        saved = json.loads(destination.read_text())
        if saved['signature'] != signature:
            raise ValueError('export resume source mismatch')
        return saved['summary']
    store = ScannerTrackingInputStore(bulk_root)
    try:
        source = store.load(scan['session_id'])
    finally:
        store.close()
    if source.input_manifest_sha256 != scan['manifest_sha256']:
        raise ValueError('capture manifest changed since cohort freeze')
    if source.sample_rate_hz != scan['sample_rate_hz'] or source.probe_ms != 20:
        raise ValueError('unexpected sample rate or probe duration')
    projected = project_scanner_candidates(source)
    raw = {}
    for probe in source.probes:
        for candidate in probe.candidates:
            if candidate.passed_fractional_margin_gate:
                key = (probe.visit_index, probe.receiver_id, probe.probe_index, candidate.candidate_rank)
                if key in raw:
                    raise ValueError('duplicate raw candidate key')
                raw[key] = (probe, candidate)
    records = []
    for point in projected:
        key = (point.visit_index, point.receiver_id, point.probe_index, point.candidate_rank)
        probe, candidate = raw[key]
        row = dict(row_index=len(records), candidate_id=point.candidate_id, group_id=point.source_group_id,
                   probe_key=list(key[:3]), candidate_rank=point.candidate_rank, channel=point.channel,
                   edge=point.edge.value, receiver=point.receiver_id, rf_hz=point.actual_rf_hz,
                   time_s=(point.support_center_utc_ns-source.timing.first_sample_estimate_utc_ns)/1e9,
                   support_start_s=(point.support_start_utc_ns-source.timing.first_sample_estimate_utc_ns)/1e9,
                   support_end_s=(point.support_end_utc_ns-source.timing.first_sample_estimate_utc_ns)/1e9,
                   probe_start_ms=probe.probe_start_ms, original_hz=point.measured_cfo_hz,
                   original_margin=point.margin, original_exact_score=point.exact_score,
                   original_control_score=point.control_score,
                   integer_epoch_sample=candidate.integer_epoch_sample,
                   fractional_epoch_offset_samples=candidate.fractional_epoch_offset_samples)
        records.append(row)
    if len({r['candidate_id'] for r in records}) != len(records):
        raise ValueError('duplicate projected IDs')
    # Probe selection is independent of signal quality; payload test is intentionally
    # only first/middle/last. Full payload coverage is verified during refinement.
    iq = AdaptiveHopIqStore(bulk_root, read_only=True)
    checked = []
    try:
        published = iq.inspect(scan['session_id'])
        if published.manifest_sha256 != scan['manifest_sha256']:
            raise ValueError('IQ manifest changed')
        available = visit_ordinals(published.manifest.receipt)
        missing_visits = sorted({p.visit_index for p in source.probes} - available.keys())
        visits = sorted({p.visit_index for p in source.probes} & available.keys())
        if not visits:
            raise ValueError('no GLRT probes')
        for index in sorted({0, len(visits)//2, len(visits)-1}):
            visit, values = read_event(iq, published, visits[index])
            if values.shape[1:] != (2, 2) or values.shape[0] < source.sample_rate_hz//50:
                raise ValueError('unexpected IQ layout')
            checked.append(dict(visit_index=visits[index], shape=list(values.shape)))
    finally:
        iq.close()
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    tle = archive.select_latest_before(source.timing.first_sample_estimate_utc_ns)
    payload, debris = exclude_labelled_starlink_debris(archive.read(tle))
    catalogue = parse_element_sets(payload)
    summary = dict(label=scan['label'], session_id=scan['session_id'], split=scan['split'],
                   sample_rate_hz=source.sample_rate_hz, projected_passing_candidates=len(records),
                   passing_windows=len({r['group_id'] for r in records}),
                   all_scheduled_probes=len(source.probes),
                   raw_passing_candidates=len(raw), projected_out_candidates=len(raw)-len(records),
                   catalogue_satellites=len(catalogue.satellite_numbers), sampled_iq_visits=checked,
                   events_without_retained_iq=missing_visits,
                   elapsed_s=time.monotonic()-started)
    output = dict(signature=signature, summary=summary, records=records,
                  origin_utc_ns=source.timing.first_sample_estimate_utc_ns,
                  analysis_manifest_sha256=source.analysis_manifest_sha256,
                  tle=dict(policy='latest archived snapshot collected strictly before capture',
                           collected_utc_ns=tle.collected_utc_ns, provider=tle.provider, sha256=tle.digest,
                           path=str(tle.path), age_s=(source.timing.first_sample_estimate_utc_ns-tle.collected_utc_ns)/1e9),
                  scope='All passing projected hypotheses, including exact aliases; no orbit inputs, no reassignment or candidate thinning. Only three IQ visits preflighted.')
    canonical(output)  # reject nonfinite metadata before creating a checkpoint
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x') as stream:
        json.dump(output, stream, allow_nan=False)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, default=OUT/'cohort-v2.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--labels', nargs='+')
    args = parser.parse_args()
    cohort_bytes = args.cohort.read_bytes()
    scans = json.loads(cohort_bytes)['scans']
    if args.labels:
        known = {r['label'] for r in scans}
        if not set(args.labels) <= known:
            raise ValueError('unknown scan label')
        scans = [r for r in scans if r['label'] in args.labels]
    for scan in scans:
        print('EXPORT', scan['label'], scan['session_id'], flush=True)
        result = export(scan, args.output/scan['label']/'observations.json', digest(cohort_bytes))
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
