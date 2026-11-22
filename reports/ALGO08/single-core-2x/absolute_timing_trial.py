"""Audit receive-time authority and the transmitter-phase gauge on saved public tracks."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path

import numpy as np

from leo.analysis.polynomial_tracklets import TrackConfig
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.qualification import cold_scenes, range_epoch_model
from tools.pipeline_eval.qualification.range_epoch_trial import native_winners

from .mirrored_noise_trial import SITES, selected_tracks
from .mirrored_orbit_weight_trial import CURVES_SHA256, curves, study, support

PAIRS_SHA256 = "5eb89ce0efed15ee545e2a34b4c0cdbc2c354fcddd064d912f3884ecc5390c19"
PHYSICAL_SHA256 = "5e29a9c9f76c93e605792915f8baffe4a28e31dbd6bd67e586c6a68821bd9a2d"
FRAME_HZ = cold_scenes.FRAME_HZ
LANE_SAMPLES = .42
TOLERANCE_SAMPLES = 2e-6


def receive_epoch(delay, transmit_phase, times, counters, rate, period, clock, lane):
    """The released generator's local ADC epoch for a repeated frame."""
    frame = np.rint((times - delay - transmit_phase) * FRAME_HZ)
    arrival = frame / FRAME_HZ + transmit_phase + delay
    return ((arrival - clock) * rate - counters + lane * LANE_SAMPLES) % period


def phase_gauge(delay, change, fitted_phase, times, counters, rate, period):
    """Shift each delay by a constant and cancel it in the transmit phase."""
    corrected = fitted_phase - change
    left = receive_epoch(delay, fitted_phase, times, counters, rate, period, 0., 0)
    right = receive_epoch(delay + change, corrected, times, counters, rate, period, 0., 0)
    errors = [range_epoch_model.wrap(right - left, period)]
    for delay_model, phase, reference in (
        (delay, fitted_phase, left), (delay + change, corrected, right),
    ):
        second = receive_epoch(delay_model, phase, times, counters, rate, period, 0., 1)
        errors.append(range_epoch_model.wrap(second - reference - LANE_SAMPLES, period))
    return float(np.max(np.abs(errors)))


def timing_fields(native):
    anchor = native["clock_anchor"]
    source = native["source"]
    candidate_fields = sorted({
        key for probe in source["probes"] for candidate in probe["candidates"] for key in candidate
    })
    return dict(
        sample_rate_hz=source["sample_rate_hz"], probe_ms=source["probe_ms"],
        capture_mode=source["capture_mode"], source_timing_present=source["timing"] is not None,
        receiver_ids=sorted({probe["receiver_id"] for probe in source["probes"]}),
        host_bracket_width_ns=anchor["after"]["realtime_ns"] - anchor["before"]["realtime_ns"],
        anchor_fields=sorted(anchor), delivery_clock_field_sets=sorted({
            tuple(sorted(clock)) for clock in native["delivery_clocks"]
        }),
        document_fields=sorted(native), source_fields=sorted(source),
        candidate_fields=candidate_fields,
        rf_authority=native["provenance"]["rf_mapping_authorities"],
    )


def inspect(site, native, config, row, pairs, reader):
    selected = selected_tracks(site, row, native, config)
    document = study.inputs.verified(native, row["native_sha256"])
    winners = native_winners(document)
    owners, receivers, times, _ = support(row["tracks"])
    exact = [winners[key] for track in selected for key in track["observation_ids"]]
    if any(r["rx"] != receiver or abs(r["time_s"] - time) > 1e-9
           for r, receiver, time in zip(exact, receivers, times, strict=True)):
        raise ValueError("Native arrival and frozen per-satellite epoch differ")
    first, second = (np.asarray(pairs[key]) for key in ("first", "second"))
    if (pairs["native_sha256"] != row["native_sha256"]
            or not np.array_equal(owners[first], owners[second])
            or not np.array_equal(times[first], times[second])
            or any(exact[a]["channel"] != exact[b]["channel"]
                   or exact[a]["rf_hz"] != exact[b]["rf_hz"]
                   for a, b in zip(first, second, strict=True))):
        raise ValueError("The stereo rows do not identify the same timed emitter and band")

    rate = document["source"]["sample_rate_hz"]
    period = rate / FRAME_HZ
    observed = np.asarray([r["phase"] for r in exact])
    stereo = range_epoch_model.wrap(observed[second] - observed[first], period)
    cutoff = document["clock_anchor"]["before"]["realtime_ns"]
    prepared = causal_catalogue(reader, cutoff)
    snapshots = sorted({r["snapshot_digest"] for r in prepared.provenance})
    source = study.arrival.pinned_packet("regional-reassignment.json.gz")[f"{site}-containing"]
    if snapshots != source["snapshots"]:
        raise ValueError("Capture-causal catalogue differs from the public owner map")
    bank = dict(zip(prepared.catalogue.satellite_numbers,
                    prepared.catalogue.satellites, strict=True))
    xyz = [geodetic_to_ecef_km(*coordinate, 0.) for coordinate in row["faces"]]
    fixed_phase = 1 / (3 * FRAME_HZ)
    satellite_rows, all_changes, all_remaining = {}, [], []
    for orbit in sorted(set(owners[first])):
        t = np.sort(times[first][owners[first] == orbit])
        (delay_a, radial_a), (delay_b, _) = [
            cold_scenes._signal(bank[orbit], row["origin_utc_ns"], t, place) for place in xyz
        ]
        changes = delay_b - delay_a
        constant = changes[0]
        counter = np.rint((t - document["source"]["probe_ms"] * .0005) * rate)
        received_period = period * (1 + radial_a / cold_scenes.LIGHT_KM_S)
        invariant = phase_gauge(
            delay_a, constant, fixed_phase, t, counter, rate, received_period,
        )
        first_at_b = receive_epoch(
            delay_b[:1], fixed_phase - constant, t[:1], counter[:1],
            rate, received_period[:1], 0., 0,
        )
        first_at_a = receive_epoch(
            delay_a[:1], fixed_phase, t[:1], counter[:1], rate, received_period[:1], 0., 0,
        )
        reference = float(np.max(np.abs(range_epoch_model.wrap(
            first_at_b - first_at_a, received_period[:1],
        ))))
        if max(invariant, reference) > TOLERANCE_SAMPLES:
            raise ValueError("A constant range change was not absorbed by transmit phase")
        remaining = (changes - constant) * rate
        all_changes.extend(changes * rate)
        all_remaining.extend(remaining)
        satellite_rows[int(orbit)] = dict(
            paired_epochs=len(t), reference_change_samples=float(constant * rate),
            fitted_phase_change_ns=float(-constant * 1e9),
            first_epoch_equivalence_error_samples=reference,
            constant_delay_and_stereo_gauge_max_error_samples=invariant,
            residual_change_rms_samples=study.rms(remaining),
        )
    return dict(
        native_sha256=row["native_sha256"], clock=timing_fields(document), faces=row["faces"],
        simultaneous_pairs=len(stereo), causal_cutoff_utc_ns=cutoff, causal_snapshots=snapshots,
        observed_stereo_offset_median_samples=float(np.median(stereo)),
        observed_stereo_residual_about_0_42_rms_samples=study.rms(stereo - LANE_SAMPLES),
        max_absolute_geometric_change_samples=float(np.max(np.abs(all_changes))),
        absolute_geometric_change_rms_samples=study.rms(all_changes),
        time_varying_change_rms_samples=study.rms(all_remaining), satellites=satellite_rows,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (*SITES, "archive", "track_config"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--physical", type=Path)
    args = parser.parse_args()
    prediction = curves()
    pair_path = study.inputs.MEASUREMENTS / "mirrored-noise-lock.json.gz"
    raw_pairs = gzip.decompress(pair_path.read_bytes())
    if sha256(raw_pairs).hexdigest() != PAIRS_SHA256:
        raise ValueError("Unexpected simultaneous receiver pairing")
    pairs = json.loads(raw_pairs)
    if pairs["curves_sha256"] != CURVES_SHA256:
        raise ValueError("Pairs differ from the causal prediction design")
    configuration = study.inputs.verified(args.track_config, study.arrival.TRACK_CONFIG)
    config = TrackConfig(**configuration["config"])
    reader = TleArchiveReader(args.archive)
    results = {site: inspect(site, getattr(args, site), config, prediction["sites"][site],
                             pairs["sites"][site], reader) for site in SITES}
    value = dict(causal_prediction_sha256=CURVES_SHA256, pairs_sha256=PAIRS_SHA256, sites=results)
    if args.physical is not None:
        native = study.inputs.verified(args.physical, PHYSICAL_SHA256)
        value["physical_metadata"] = timing_fields(native) | {"native_sha256": PHYSICAL_SHA256}
    print(json.dumps(value, allow_nan=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
