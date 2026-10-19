"""Read-only replay of phase and range receipts, never execute old generators."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import time
import numpy as np
from phase_math import relative_counter, arrival_phase_samples, first_frame_time_s, unwrap_phase_samples, linear_detrend

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
OLD = REPORTS/'three-track-20261016'
ROOT = Path('/tmp/three-track-investigation/space-track-pipeline-rerun')


def sha(path):
    return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {k:plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [plain(v) for v in value]
    return value


def main():
    from leo.storage.shared_fast_scan import SharedFastScanStore
    from leo.cli.shared_fast_position import load_input
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.contracts.regional_position import PositionObservations, RegionalPrior
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import observer, LIGHT_KM_S, zero_sum_basis
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    started = time.monotonic()
    copies = {}
    (HERE/'originals').mkdir(exist_ok=True)
    for name in ['frame_phase_crossband.py', 'frame_range_consistency.py', 'frame_epoch_sign_control.py', 'compare_space_track_pipeline.py']:
        original = Path('/tmp')/name
        copied = HERE/'originals'/name
        if copied.exists():
            assert copied.read_bytes() == original.read_bytes()
        else:
            copied.write_bytes(original.read_bytes())
        copies[str(original)] = dict(sha256=sha(original), preserved_as=str(copied.relative_to(HERE)))
    old_manifest = json.loads((OLD/'manifest.json').read_text())
    files = {r['path']:r for r in old_manifest['files']}
    evidence_names = ['frame_phase_crossband.json', 'frame_range_consistency.json', 'frame_epoch_sign_control.json',
        'comparison_manifest.json', 'late_track_extension.json', 'timing_prior_compressed_0p5s.json']
    bindings = {}
    for name in evidence_names:
        copied = OLD/'evidence'/name
        assert copied.read_bytes() == (ROOT/name).read_bytes()
        assert sha(copied) == 'sha256:'+files['evidence/'+name]['sha256']
        bindings[name] = sha(copied)
    provenance = json.loads((OLD/'evidence/comparison_manifest.json').read_text())
    job, document, original_terminal, _ = SharedFastScanStore('/srv/bulk/leo', 'shared-scan-q-v2').plot_evidence(provenance['baseline_job'])
    source = load_input(document)
    assert original_terminal['input_sha256'] == 'sha256:'+provenance['input_sha256']
    fs = source.sample_rate_hz
    assert isinstance(fs, int)
    winners = {}
    for p in project_scanner_candidates(source):
        previous = winners.get(p.source_group_id)
        if previous is None or (-p.margin, p.candidate_rank, p.candidate_id) < (-previous.margin, previous.candidate_rank, previous.candidate_id):
            winners[p.source_group_id] = p
    points = sorted(winners.values(), key=lambda p:(p.support_center_utc_ns, p.source_group_id))
    origin = source.timing.first_sample_estimate_utc_ns
    times = np.array([(p.support_center_utc_ns-origin)/1e9 for p in points])
    probes = {(p.visit_index, p.receiver_id, p.probe_index):p for p in source.probes}
    phase, first, counter, epochs, fractional = [], [], [], [], []
    for p in points:
        probe = probes[p.visit_index, p.receiver_id, p.probe_index]
        candidate = next(c for c in probe.candidates if c.candidate_rank == p.candidate_rank)
        c = relative_counter(probe.valid_start_counter, source.timing.session_start_device_sample_counter, probe.probe_start_ms, fs)
        counter.append(c);epochs.append(candidate.integer_epoch_sample);fractional.append(candidate.fractional_epoch_offset_samples)
        phase.append(arrival_phase_samples(c, candidate.integer_epoch_sample, candidate.fractional_epoch_offset_samples, fs))
        first.append(first_frame_time_s(c, candidate.integer_epoch_sample, candidate.fractional_epoch_offset_samples, fs))
    phase, first = np.array(phase), np.array(first)
    channel = np.array([p.channel for p in points]);rx = np.array([p.receiver_id for p in points])
    cross = json.loads((OLD/'evidence/frame_phase_crossband.json').read_text())
    ranged = json.loads((OLD/'evidence/frame_range_consistency.json').read_text())

    def match(sought, axis, *, ch, receiver=None):
        chosen = []
        for t in sought:
            candidates = np.flatnonzero((abs(axis-t) <= 1e-10) & (channel == ch)
                & ((rx == receiver) if receiver is not None else True))
            if len(candidates) != 1:
                raise ValueError('Frozen metadata time does not identify one original candidate')
            chosen.append(int(candidates[0]))
        return np.array(chosen)

    cross_replay, all_rows = [], []
    for record in cross['records']:
        ch = int(record['channel'][2:])
        rows = match(record['times_s'], times, ch=ch)
        all_rows.extend(rows)
        if ch == int(cross['records'][0]['channel'][2:]):
            np.testing.assert_array_equal(rows, json.loads((OLD/'evidence/late_track_extension.json').read_text())['selected_rows'])
        rebuilt = unwrap_phase_samples(phase[rows], fs)
        np.testing.assert_allclose(rebuilt, record['phase_samples'], atol=1e-9, rtol=0)
        coef = np.polyfit(times[rows]-185., rebuilt, 2)
        np.testing.assert_allclose(coef, record['quadratic_coefficients'], atol=1e-9, rtol=0)
        cross_replay.append(dict(channel=record['channel'], rows=rows,
            max_phase_error_samples=float(np.max(abs(rebuilt-record['phase_samples']))),
            maximum_unwrapped_step_samples=float(np.max(abs(np.diff(rebuilt)))),
            smallest_gap_s=float(np.min(np.diff(times[rows]))), largest_gap_s=float(np.max(np.diff(times[rows]))),
            support_center_minus_first_frame_s=dict(minimum=float(np.min(times[rows]-first[rows])),
                maximum=float(np.max(times[rows]-first[rows]))),
            phase_crosses_modulo_seam=bool(np.any(abs(np.diff(phase[rows])) > fs/750/2)),
            integer_epoch_range=[int(np.min(np.array(epochs)[rows])), int(np.max(np.array(epochs)[rows]))],
            fractional_offset_range=[float(np.min(np.array(fractional)[rows])), float(np.max(np.array(fractional)[rows]))]))

    terminal = json.loads((ROOT/'output/terminal.json').read_text())
    assert terminal['input_sha256'] == original_terminal['input_sha256']
    assert terminal['provenance']['tle_sha256'] == provenance['snapshot_digest']
    fit = json.loads((OLD/'evidence/timing_prior_compressed_0p5s.json').read_text())['fit']
    v = np.array(fit['vector']);numbers = list(map(int, terminal['candidate_numbers']))
    prior = RegionalPrior(**terminal['provenance']['prior'])
    obs = PositionObservations(tuple(p.source_group_id for p in points), times, np.zeros(len(points)),
        np.array([p.actual_rf_hz for p in points]), rx, channel, np.ones(len(points)))
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshot = next(s for s in archive.list_snapshots() if s.digest == provenance['snapshot_digest'])
    assert snapshot.provider == provenance['provider'] and snapshot.collected_utc_ns == provenance['collected_utc_ns']
    catalogue = parse_element_sets(archive.read(snapshot));lookup = {int(n):i for i, n in enumerate(catalogue.satellite_numbers)}
    bank, bank_receipt = build_regional_bank(catalogue, [lookup[n] for n in numbers], origin, obs, prior, maximum_seconds=90.)
    lookup = {int(n):i for i, n in enumerate(bank.numbers)};bank = bank.select([lookup[n] for n in numbers])
    shifts = v[7]+zero_sum_basis(len(numbers))@v[8:];site = observer(prior, v[:2])[0]
    range_replay = []
    for record in ranged['records']:
        label = re.fullmatch(r'(\d+) RX(\d+) CH(\d+)', record['label'])
        if label is None: raise ValueError('Unknown frozen descriptive label')
        number, receiver, ch = map(int, label.groups())
        rows = match(record['times_s'], first, ch=ch, receiver=receiver-1)
        all_rows.extend(rows)
        t = first[rows];rebuilt = unwrap_phase_samples(phase[rows], fs)
        k = numbers.index(number);q = t+shifts[k]
        assert np.all((q >= bank.nodes_s[0]) & (q <= bank.nodes_s[-1]))
        position = np.column_stack([np.interp(q, bank.nodes_s, bank.position_km[k, :, j]) for j in range(3)])
        delay = np.linalg.norm(position-site, axis=1)/LIGHT_KM_S*fs
        observed = linear_detrend(t, rebuilt);geometric = linear_detrend(t, delay)
        np.testing.assert_allclose(observed, record['observed_detrended_samples'], atol=1e-8, rtol=0)
        np.testing.assert_allclose(geometric, record['range_detrended_samples'], atol=1e-8, rtol=0)
        positive = float(np.sqrt(np.mean((observed-geometric)**2)))
        negative = float(np.sqrt(np.mean((observed+geometric)**2)))
        np.testing.assert_allclose([positive, negative], [record['positive_range_rms_samples'], record['negative_range_rms_samples']], atol=1e-8, rtol=0)
        range_replay.append(dict(label=record['label'], rows=rows,
            max_phase_detrend_error_samples=float(np.max(abs(observed-record['observed_detrended_samples']))),
            max_range_detrend_error_samples=float(np.max(abs(geometric-record['range_detrended_samples']))),
            positive_range_rms_samples=positive, negative_range_rms_samples=negative,
            maximum_unwrapped_step_samples=float(np.max(abs(np.diff(rebuilt)))),
            time_span_s=float(np.ptp(t)), observed_curvature_samples_s2=float(2*np.polyfit(t-t.mean(), rebuilt, 2)[0]),
            geometric_curvature_samples_s2=float(2*np.polyfit(t-t.mean(), delay, 2)[0])))
    selected = np.unique(all_rows)
    result = dict(generator_found=True, original_generators=copies, frozen_evidence_sha256=bindings,
        historical_generator_integrity='Original report did not hash these /tmp scripts. Current surviving bytes are preserved and semantic receipt reconstruction succeeds; historical byte immutability is not claimed.',
        phase_definition='Positive arrival epoch modulo Fs/750; no sign inversion. Relative integer counters are differenced before floating fractional epoch addition.',
        phase_formula='(((counter*750)%Fs)/750 + integer_epoch + fractional_offset) % (Fs/750)',
        sample_rate_hz=fs, physical_period_samples=fs/750, acquisition_ring_cells=round(fs/750),
        source_input_sha256=terminal['input_sha256'], analysis_manifest_sha256=source.analysis_manifest_sha256,
        session_start_counter=source.timing.session_start_device_sample_counter,
        relative_counter_range=[min(counter), max(counter)],selected_rows=len(selected),
        selected_epochs_near_rounded_acquisition_seam=int(np.sum((np.array(epochs)[selected] <= 2)
            | (np.array(epochs)[selected] >= round(fs/750)-3))),
        crossband=cross_replay, range_comparison=range_replay, bank_receipt=asdict(bank_receipt),
        synthetic_sign_control=json.loads((OLD/'evidence/frame_epoch_sign_control.json').read_text()),
        elapsed_seconds=time.monotonic()-started,
        code_sha256={name:sha(HERE/name) for name in ['phase_math.py', 'audit.py']},
        qualification='Existing selected-row evidence replay only. No raw IQ, acquisition campaign, localization fit, changed IDs/window rules or physical transmitter/hardware conclusion. Negative geometric relation is not a negation in phase formula; transmitted epoch/cycle identity and selected orbit identity remain unproved.')
    with (HERE/'audit.json').open('x') as stream:
        json.dump(plain(result), stream, indent=2, allow_nan=False);stream.write('\n')
    print(json.dumps(plain(result), indent=2))


if __name__ == '__main__':
    main()
