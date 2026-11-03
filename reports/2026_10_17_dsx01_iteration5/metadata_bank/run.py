"""Freeze metadata-only catalogue eligibility, then audit descriptive overlap."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import numpy as np

from metadata import MAXIMUM_CANDIDATES, observation_metadata, cap_bank

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
COLD = REPORTS/'2026_10_17_dsx01_iteration4/cold_pipeline/S03-early_to_late'
DATA = REPORTS/'2026_10_16_dsx01_fast_association_losses'


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def sha(path):
    return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.contracts.regional_position import RegionalPrior
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets, parse_element_set_records

    started = time.monotonic()
    derivation = json.loads((COLD/'derivation.json').read_text())
    provenance = json.loads((COLD/'output/terminal.json').read_text())['provenance']
    prior = RegionalPrior(**provenance['prior'])
    # Project metadata before constructing observations. No measured CFO, signal
    # strength, selected IDs, position estimate or station reference is read.
    rows = [r for line in (DATA/'context-observations.jsonl').read_text().splitlines()
        if (r := json.loads(line))['source_id'] == 'S03']
    observations, projected = observation_metadata(rows)
    del rows
    source = next(s for s in json.loads((DATA/'sources.json').read_text()) if s['source_id'] == 'S03')
    origin = source['first_sample_estimate_utc_ns']
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    binding = derivation['causal_tle']
    snapshots = [s for s in archive.list_snapshots() if s.digest == binding['sha256']
        and s.provider == binding['provider'] and s.collected_utc_ns == binding['collected_utc_ns']]
    if len(snapshots) != 1 or snapshots[0].collected_utc_ns >= origin:
        raise ValueError('Unique matching causal snapshot required')
    text = archive.read(snapshots[0])
    input_records = parse_element_set_records(text)
    filtered, debris = exclude_labelled_starlink_debris(text)
    records = parse_element_set_records(filtered)
    catalogue = parse_element_sets(filtered)
    indices = [i for i, record in enumerate(records) if record.name.upper().startswith('STARLINK')]
    nonstarlink = [record.satellite_number for record in records if not record.name.upper().startswith('STARLINK')]
    bank, receipt = build_regional_bank(catalogue, indices, origin, observations, prior,
        maximum_seconds=90., batch_size=128)
    bank, cap = cap_bank(bank, prior)
    bank_path = HERE/'metadata-bank.npz'
    if bank_path.exists():
        raise FileExistsError('Never overwrite a frozen bank')
    np.savez_compressed(bank_path, numbers=bank.numbers, nodes_s=bank.nodes_s,
        position_km=bank.position_km, velocity_km_s=bank.velocity_km_s)
    freeze = dict(source_id='S03', phase='metadata-only bank frozen before selected-ID/label audit',
        source_tracking_input_sha256=source['tracking_input_sha256'], origin_utc_ns=origin,
        metadata_sha256='sha256:'+hashlib.sha256(json.dumps(projected, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        known_observations=len(projected), prior=asdict(prior), causal_tle=binding,
        catalogue_input_count=len(input_records), explicit_starlink_debris_count=len(debris),
        explicit_starlink_debris=[asdict(d) for d in debris],
        nonstarlink_excluded_count=len(nonstarlink), nonstarlink_excluded_numbers=list(map(int, nonstarlink)),
        starlink_propagated_count=len(indices), regional=asdict(receipt), cap=cap,
        rf_metadata=dict(minimum_hz=float(observations.rf_hz.min()), maximum_hz=float(observations.rf_hz.max()),
            distinct_actual_rf_hz=list(map(float, np.unique(observations.rf_hz))),
            qualification='Actual RF preserved; catalogue port carries no transmitter-band authority. No invented per-ID RF filter.'),
        node_policy='Public0.25s whole-known-time propagation with21s padding each side, conservative visibility over entire250km regional prior.',
        selected_numbers=list(map(int, bank.numbers)), bank_sha256=sha(bank_path),
        bank_file_bytes=bank_path.stat().st_size,
        elapsed_seconds_before_label_audit=time.monotonic()-started,
        code_sha256={name:sha(HERE/name) for name in ['metadata.py', 'run.py']},
        qualification='Candidate eligibility prototype only. No measured CFO, labels, station location, fit, q or timing inference enters membership. Fixed1024cap derives from prior measured708 train-regional count, not this audit outcome.')
    save(HERE/'freeze.json', freeze)

    # Only after the bank and its provenance are persisted do selected IDs and
    # full-recording-conditioned labels enter this descriptive audit.
    cold = json.loads((COLD/'evaluation.json').read_text())
    original = json.loads((REPORTS/'2026_10_16_dsx01_models/results/S03-full-fitted-c-original.json').read_text())
    points = dict(np.load(REPORTS/'2026_10_16_dsx01_models/results/S03-full-fitted-c-original.npz'))
    masks = dict(np.load(COLD/'evaluation.npz'))
    np.testing.assert_array_equal(points['times_s'], observations.times_s)
    np.testing.assert_array_equal(masks['times_s'], observations.times_s)
    retained = set(map(int, bank.numbers))
    original_ids = set(map(int, original['full_scan']['total_timing_s']))
    cold_ids = set(cold['training_selected_numbers'])
    label_covered = np.isin(points['satellite_number'], bank.numbers)
    scopes = {}
    for label, mask in [('train', masks['train_mask']), ('held', masks['held_mask'])]:
        use = mask & points['associated']
        scopes[label] = dict(original_assigned=int(use.sum()), original_winner_covered=int((use & label_covered).sum()),
            original_winner_missing=int((use & ~label_covered).sum()))
    audit = dict(freeze_sha256=sha(HERE/'freeze.json'), bank_sha256=sha(bank_path),
        retained_count=len(retained), original_full_count=len(original_ids), cold_selected_count=len(cold_ids),
        original_full_overlap=len(retained & original_ids), cold_selected_overlap=len(retained & cold_ids),
        original_full_missing_numbers=sorted(original_ids-retained), cold_selected_missing_numbers=sorted(cold_ids-retained),
        scopes=scopes, elapsed_seconds_total=time.monotonic()-started,
        qualification='Post-freeze descriptive original-label coverage only, not satellite truth, predictive assignment, recovery, false-positive rate, localization or model score. No fit performed.')
    save(HERE/'overlap.json', audit)
    print(json.dumps(dict(eligible=len(bank.numbers), catalogue=len(input_records), propagated=len(indices),
        regional_invalid=len(receipt.invalid_numbers), outside_prior=len(receipt.outside_prior_numbers),
        cap_rejected=len(cap['cap_excluded_numbers']), **audit), indent=2))


if __name__ == '__main__':
    main()
