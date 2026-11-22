"""Compare a fixed historical Doppler direction with an isotropic face score."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

import numpy as np

from leo.analysis.polynomial_tracklets import TrackConfig
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.localization_v3_inputs import prepare_phase_history
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.qualification import range_epoch_model
from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser

from . import mirrored_causal_forecast_trial as causal
from .mirrored_noise_trial import selected_tracks
from .mirrored_orbit_weight_trial import CURVES_SHA256, curves, support

study = causal.study
STEREO_LOCK = "ed599f98d595e6d9f975c7df05f27b6e3d7a11476a27643256a987bc242eced1"
SITES = ("north", "south")
SOURCES = ("later_A", "later_B", "observed")


def lift_observed(values, nominal):
    """Return one common midpoint lift and count rows with unequal A/B aliases."""
    period = range_epoch_model.FOLD_HZ
    displacement = values[:, None] - nominal
    turns = np.floor((displacement + period / 2) / period)
    differences = int(np.count_nonzero(np.any(turns != turns[:, 1:2], axis=1)))
    lifted = values - period * turns[:, 1]
    return lifted, differences


def fit_revision(revision, sigma, residual):
    """Return the ridge residual and unit-prior coefficients in the projected space."""
    normal = np.eye(revision.shape[1]) * sigma**2 + revision.T @ revision
    coefficient = np.linalg.solve(normal, revision.T @ residual)
    return residual - revision @ coefficient, coefficient


def information(revision, sigma, direction):
    residual, _ = fit_revision(revision, sigma, direction)
    original = direction @ direction
    if original <= 0.0:
        raise ValueError("The ordinary nuisance design removes the entire face direction")
    return float((direction @ residual) / original)


def score(templates, data, revision, sigma):
    delta = (data[:, :, None] - templates[:, None, :]).reshape(len(data), -1)
    adjusted, coefficient = fit_revision(revision, sigma, delta)
    frequency_mse = np.mean(adjusted**2, axis=0).reshape(-1, 2)
    penalty_mse = (sigma**2 / len(data) * np.sum(coefficient**2, axis=0)).reshape(-1, 2)
    loss = frequency_mse + penalty_mse
    return {
        name: dict(
            penalized_equivalent_rms_hz=np.sqrt(row).tolist(),
            fitted_rms_hz=np.sqrt(frequency).tolist(),
            B_minus_A_hz2=float(row[1] - row[0]),
            preferred="A" if row[0] < row[1] else "B" if row[1] < row[0] else "tie",
        )
        for name, row, frequency in zip(SOURCES[: len(loss)], loss, frequency_mse, strict=True)
    }


def lock_inputs(prediction, native, archive, track_config):
    stereo = causal.checked_lock(
        study.inputs.MEASUREMENTS / "mirrored-orbit-weights.json",
        STEREO_LOCK,
    )
    if stereo["curves_sha256"] != CURVES_SHA256:
        raise ValueError("The stereo scale was measured for a different face curve lock")
    config = TrackConfig(
        **study.inputs.verified(track_config, study.arrival.TRACK_CONFIG)["config"]
    )
    cutoff = prediction["causal_cutoff_utc_ns"]
    parser = CausalPreparationParser()
    current = causal_catalogue(archive, cutoff, element_parser=parser)
    catalogue = current.catalogue
    satellites = dict(zip(catalogue.satellite_numbers, catalogue.satellites, strict=True))
    epochs = {row["norad"]: row["element_epoch_utc_ns"] for row in current.provenance}
    snapshots = sorted({row["snapshot_digest"] for row in current.provenance})
    numbers = {
        str(track["norad"]): None for row in prediction["sites"].values() for track in row["tracks"]
    }
    metadata = dict(causal_cutoff_utc_ns=cutoff, anchor_utc_ns=cutoff)
    history = prepare_phase_history(archive, numbers, metadata, element_parser=parser)[
        "past_versions"
    ]
    result = {}
    for site in SITES:
        row = prediction["sites"][site]
        prior = stereo["sites"][site]
        selection = selected_tracks(site, row, native[site], config)
        frozen = study.arrival.pinned_packet("regional-reassignment.json.gz")[f"{site}-containing"]
        if snapshots != frozen["snapshots"]:
            raise ValueError("Capture-time orbit authority differs from the fixed owner map")
        owners, receivers, times, design = support(row["tracks"])
        origin = row["origin_utc_ns"]
        midpoint = geodetic_to_ecef_km(*np.mean(row["faces"], axis=0), 0.0)
        previous = {}
        for n in np.unique(owners):
            receipt, preceding, _ = causal.receipts(
                satellites[n], epochs[n], history[str(n)], origin
            )
            if preceding is None or receipt["previous_epoch_gap_s"] != prior["epoch_gap_s"][str(n)]:
                raise ValueError("Expected the preceding element epoch from the historical lock")
            previous[n] = preceding
        old = np.concatenate(
            [
                causal.frequency(
                    previous[t["norad"]], origin, np.asarray(t["times"]), t["rf"], midpoint
                )
                for t in row["tracks"]
            ]
        )
        nominal = np.concatenate([t["predictions"]["nominal"] for t in row["tracks"]])
        revision = nominal[:, 1] - old
        projected, _ = study.project(design, revision)
        for n in np.unique(owners):
            mse = np.mean(projected[owners == n] ** 2)
            if not np.isclose(mse, prior["variance"][str(n)], rtol=1e-10, atol=1e-10):
                raise ValueError("Recomputed Doppler disagreement differs from the historical lock")
        values = np.concatenate([track["values"] for track in selection])
        channels = np.repeat(
            [t["channel"] for t in selection], [len(t["times"]) for t in selection]
        )
        first, second = study.simultaneous_pairs(owners, channels, times, receivers)
        difference = range_epoch_model.wrap(
            values[first] - values[second], range_epoch_model.FOLD_HZ
        )
        noise, _ = study.project(design[first] - design[second], difference / np.sqrt(2.0))
        if len(first) != prior["pairs"] or not np.isclose(np.mean(noise**2), prior["stereo_mse"]):
            raise ValueError("Stereo scale differs from the fixed historical lock")
        observed, alias_disagreements = lift_observed(values, nominal)
        result[site] = dict(
            native_sha256=row["native_sha256"],
            rows=len(times),
            stereo_pairs=len(first),
            sigma_hz=float(np.sqrt(prior["stereo_mse"])),
            revision_hz=revision.tolist(),
            observed_hz=observed.tolist() if alias_disagreements == 0 else None,
            alias_disagreements=alias_disagreements,
        )
    return dict(
        curves_sha256=CURVES_SHA256,
        stereo_lock_sha256=STEREO_LOCK,
        snapshots=snapshots,
        causal_cutoff_utc_ns=cutoff,
        sites=result,
    )


def compare(design, values, source_count, sigma):
    projected, rank = study.project(design, values)
    split = 2 + source_count
    if np.max(np.abs(projected[:, split])) > 1e-9:
        raise ValueError("Track offsets did not absorb the fitted calibration column")
    templates = projected[:, :2]
    sources = projected[:, 2:split]
    revision = projected[:, split + 1 :]
    return dict(
        nuisance_rank=rank,
        retained_information=information(revision, sigma, templates[:, 1] - templates[:, 0]),
        independent=score(templates, sources, revision[:, :0], sigma),
        revision=score(templates, sources, revision, sigma),
    )


def evaluate(prediction, lock, later):
    output = {}
    for site in SITES:
        row, locked = prediction["sites"][site], lock["sites"][site]
        if row["native_sha256"] != locked["native_sha256"]:
            raise ValueError("Observed frequencies must match the fixed face support")
        tracks = row["tracks"]
        observers = [geodetic_to_ecef_km(*face, 0.0) for face in row["faces"]]
        truth = np.concatenate(
            [
                np.column_stack(
                    [
                        causal.frequency(
                            later[t["norad"]],
                            row["origin_utc_ns"],
                            np.asarray(t["times"]),
                            t["rf"],
                            observer,
                        )
                        for observer in observers
                    ]
                )
                for t in tracks
            ]
        )
        owners, _, _, design = support(tracks)
        labels = np.unique(owners)
        nominal = np.concatenate([t["predictions"]["nominal"] for t in tracks])[:, [0, 2]]
        revision = np.equal.outer(owners, labels) * np.asarray(locked["revision_hz"])[:, None]
        observed = locked["observed_hz"]
        data = truth if observed is None else np.column_stack((truth, observed))
        calibration = np.repeat(
            [t["rf"] / 1e9 - 11.5 for t in tracks], [len(t["times"]) for t in tracks]
        )
        sigma = locked["sigma_hz"]
        if not (np.isfinite(sigma) and sigma > 0 and len(owners) == locked["rows"]):
            raise ValueError("Expected the locked rows and positive stereo scale")

        values = np.column_stack((nominal, data, calibration, revision))
        output[site] = dict(
            faces=row["faces"],
            sigma_hz=sigma,
            tracks=len(tracks),
            rows=len(owners),
            norads=labels.tolist(),
            stereo_pairs=locked["stereo_pairs"],
            alias_disagreements=locked["alias_disagreements"],
            full=compare(design, values, data.shape[1], sigma),
            leave_one_orbit_out={
                int(n): compare(design[owners != n], values[owners != n], data.shape[1], sigma)
                for n in labels
            },
        )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    freeze = sub.add_parser("freeze")
    for name in (*SITES, "archive", "track_config", "output"):
        freeze.add_argument(name, type=Path)
    reveal = sub.add_parser("score")
    reveal.add_argument("lock", type=Path)
    reveal.add_argument("sha256")
    args = parser.parse_args()
    prediction = curves()
    if args.stage == "freeze":
        native = {site: getattr(args, site) for site in SITES}
        locked = lock_inputs(prediction, native, TleArchiveReader(args.archive), args.track_config)
        raw = json.dumps(locked, sort_keys=True, allow_nan=False).encode()
        with args.output.open("xb") as stream:
            stream.write(raw)
        print(sha256(raw).hexdigest())
    else:
        locked = causal.checked_lock(args.lock, args.sha256)
        if locked["curves_sha256"] != CURVES_SHA256 or locked["stereo_lock_sha256"] != STEREO_LOCK:
            raise ValueError(
                "The revision model was locked against different curve or stereo inputs"
            )
        later, authority = study.later_elements()
        if authority["collection_utc_ns"] <= max(
            v["origin_utc_ns"] for v in prediction["sites"].values()
        ):
            raise ValueError("The scoring-only generator orbit must follow both public captures")
        result = dict(
            revision_lock_sha256=args.sha256,
            later=authority,
            sites=evaluate(prediction, locked, later),
        )
        print(json.dumps(result, sort_keys=True, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
