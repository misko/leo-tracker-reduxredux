"""Seal Watson spectrum predictions before evaluating the station position."""

import argparse
import gzip
import json
from datetime import UTC, datetime
from hashlib import sha256
from itertools import product
from pathlib import Path

import numpy as np

from ..scoring import distance_km
from ..variants import external_spectrum as scans
from ..variants import external_spectrum_position as position
from . import external_spectrum_source as source

DEVELOPMENT = "230316"
HELD = ("230314", "230323")
OFF_BAND = "230302"
DURATION = 1800
CLOCKS = (0, -10, 10, -20, 20, -30, 30)
LAT_STEP, LON_STEP = 0.25, 0.375
LAT_FIRST, LON_FIRST = 49.5, -9.0
TILE_SHAPE = (48, 32)
OUTSIDE_KM = 60.0
SEED = b"watson-spectrum-tile-offers-2026-11-19"
REQUIRED_SUPPORT = 3
MAX_LOSS = 0.50
REQUIRED_MARGIN = 0.06
METHODS = (
    "spectrum",
    "directional",
    "time_shuffle",
    "oneweb",
    "geometry",
    "no_detection",
    "off_band",
)


def serialize(obj):
    return (json.dumps(obj, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n").encode()


def preserve(path, content):
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"sealed output differs: {path}")
    else:
        with path.open("xb") as handle:
            handle.write(content)


def grid():
    lat = LAT_FIRST + (np.arange(TILE_SHAPE[0]) + 0.5) * LAT_STEP
    lon = LON_FIRST + (np.arange(TILE_SHAPE[1]) + 0.5) * LON_STEP
    return position.Sites.from_degrees(np.array(list(product(lat, lon))))


def offer_pairs():
    offers = {}
    for i, j in product(*(range(n) for n in TILE_SHAPE)):
        digest = sha256(SEED + bytes((i, j))).digest()
        di = 4 if digest[0] % 2 else -4
        dj = 4 if digest[1] % 2 else -4
        bound_i, bound_j = TILE_SHAPE
        if not (
            0 <= i - di < bound_i
            and 0 <= i + di < bound_i
            and 0 <= j - dj < bound_j
            and 0 <= j + dj < bound_j
        ):
            continue
        anchor = i * bound_j + j
        decoys = [anchor + di * bound_j, anchor + dj, anchor + di * bound_j + dj]
        offers[anchor] = {
            "present": sorted([anchor, *decoys]),
            "omitted": sorted([anchor - di * bound_j - dj, *decoys]),
        }
    return offers


def timestamp(day, hour):
    return int(datetime.strptime(f"{day} {hour:02d}", "%y%m%d %H").replace(tzinfo=UTC).timestamp())


def input_windows(directory, day, band=scans.SCAN_FIELDS):
    cutoff = timestamp(day, 0) * position.NANOSECOND
    catalogs = {}
    for family in ("starlink", "oneweb"):
        text = (directory / f"{day}-{family}.tle").read_text()
        catalogs[family] = position.eligible_elements(text, cutoff)
    windows = []
    for hour in source.HOURS:
        start = timestamp(day, hour)
        path = directory / f"{day}-Kerberos_{day}_{hour:02d}00.csv"
        spectrum = scans.read_spectrum(path, start, DURATION, band)
        windows.append(
            (f"{day}-{hour:02d}", start, spectrum, scans.extract_ridges(spectrum), catalogs)
        )
    return windows


def tune_clock(windows, sites):
    results = []
    if not all(window[3] for window in windows):
        print(
            "development clock unresolved because an independent window has no usable ridges",
            flush=True,
        )
        return 0, results
    for clock in CLOCKS:
        values = [
            position.grid_scores(ridges, sites, cats["starlink"][0], clock)["loss"]
            for _, _, _, ridges, cats in windows
        ]
        best = float(np.mean(values, axis=0).min())
        results.append(dict(clock_s=clock, loss=best))
        print(f"development clock {clock:+d} s loss {best:.5f}", flush=True)
    return min(results, key=lambda row: row["loss"])["clock_s"], results


def rank_mode(mode, sites, catalogues, ridges, start, clock):
    control_shifts = (
        position.scramble_times(ridges, start, DURATION) if mode == "time_shuffle" else None
    )
    members = () if mode == "no_detection" else ridges
    satellites = catalogues["oneweb" if mode == "oneweb" else "starlink"][0]
    scores = position.grid_scores(
        members, sites, satellites, clock, control_shifts, directional=mode == "directional"
    )
    if mode == "geometry":
        geometry = scores["geometry"]
        return dict(
            loss=(1 - geometry).round(8).tolist(),
            forced=int(geometry.argmax()) if np.ptp(geometry) else None,
            eligible=False,
            support=0,
            margin=None,
            early_khz=None,
            held_khz=None,
        )
    loss = scores["loss"]
    if not np.ptp(loss):
        return dict(
            loss=loss.round(8).tolist(),
            forced=None,
            eligible=False,
            support=0,
            margin=0.0,
            early_khz=None,
            held_khz=None,
            assignments=[],
        )
    best = int(loss.argmin())
    lat, lon = sites.coordinates[best]
    away = (
        np.array([distance_km((lat, lon), tuple(row)) for row in sites.coordinates]) >= OUTSIDE_KM
    )
    margin = float(loss[away].min(initial=1) - loss[best])
    support = int(scores["support"][best])
    eligible = bool(
        support >= REQUIRED_SUPPORT and loss[best] <= MAX_LOSS and margin >= REQUIRED_MARGIN
    )
    early, late = scores["early"][:, best], scores["late"][:, best]
    finite = np.isfinite(early + late)
    early_khz = float(np.sqrt(np.median(early[finite])) / 1000) if finite.any() else None
    late_khz = float(np.sqrt(np.median(late[finite])) / 1000) if finite.any() else None
    owners = scores["ids"][:, best].tolist()
    return dict(
        loss=loss.round(8).tolist(),
        forced=best,
        eligible=eligible,
        support=support,
        margin=margin,
        early_khz=early_khz,
        held_khz=late_khz,
        assignments=owners,
    )


def verify_input(files):
    raw = (files / "source.json").read_bytes()
    manifest = json.loads(raw)
    for row in manifest["members"]:
        content = (files / row["local"]).read_bytes()
        if sha256(content).hexdigest() != row["sha256"]:
            raise ValueError(f"source member digest differs: {row['local']}")
    return raw


def predict(files, report):
    report.mkdir(parents=True, exist_ok=True)
    receipts = verify_input(files)
    sites = grid()
    development = input_windows(files, DEVELOPMENT)
    coarse = position.Sites.from_degrees(
        sites.coordinates.reshape(*TILE_SHAPE, 2)[::2, ::2].reshape(-1, 2)
    )
    clock, calibration = tune_clock(development, coarse)
    config = dict(
        calibration=calibration,
        development_ridges={window[0]: len(window[3]) for window in development},
        locked_clock_s=clock,
        duration_s=DURATION,
        grid=sites.coordinates.tolist(),
        coarse_grid=coarse.coordinates.tolist(),
        offers=offer_pairs(),
        support=REQUIRED_SUPPORT,
        max_loss=MAX_LOSS,
        margin=REQUIRED_MARGIN,
        far_km=OUTSIDE_KM,
    )
    outputs, ridges_archive = [], []
    for day in (*HELD, OFF_BAND):
        band = scans.OFF_BAND_FIELDS if day == OFF_BAND else scans.SCAN_FIELDS
        for window, start, spectrum, ridges, catalogs in input_windows(files, day, band):
            results = {}
            modes = ("off_band",) if day == OFF_BAND else METHODS[:-1]
            for mode in modes:
                result = rank_mode(mode, sites, catalogs, ridges, start, clock)
                results[mode] = result
                print(
                    f"{window} {mode} ridges={len(ridges)} "
                    f"best={result['forced']} support={result['support']}",
                    flush=True,
                )
            outputs.append(
                dict(
                    window=window,
                    if_grid=band,
                    rows=len(spectrum.utc),
                    ridges=len(ridges),
                    catalogues={
                        name: [len(items[0]), items[1]] for name, items in catalogs.items()
                    },
                    modes=results,
                )
            )
            ridges_archive.append(
                dict(
                    window=window,
                    ridges=[
                        dict(
                            utc=ridge.utc.tolist(),
                            hz=ridge.frequency_hz.tolist(),
                            db=ridge.power_db,
                            fit_hz=ridge.residual_hz,
                        )
                        for ridge in ridges
                    ],
                )
            )
    retain = files / f"{HELD[0]}-Kerberos_{HELD[0]}_{source.HOURS[0]:02d}00.csv"
    with retain.open("rb") as handle:
        sample = b"".join(handle.readline() for _ in range(60))
    code = {
        str(Path(module.__file__).relative_to(Path.cwd())): sha256(
            Path(module.__file__).read_bytes()
        ).hexdigest()
        for module in (scans, source, position)
    }
    code[str(Path(__file__).relative_to(Path.cwd()))] = sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    packed = {
        "PROTOCOL.md": (report / "PROTOCOL.md").read_bytes(),
        "source.json": receipts,
        "config.json.gz": gzip.compress(serialize(config), mtime=0),
        "ridges.json.gz": gzip.compress(serialize(ridges_archive), mtime=0),
        "predictions.json.gz": gzip.compress(serialize(outputs), mtime=0),
        "first-minute-230314-0600.csv.gz": gzip.compress(sample, mtime=0),
    }
    for name, content in packed.items():
        preserve(report / name, content)
    preserve(
        report / "prediction-lock.json",
        serialize(
            dict(
                files={name: sha256(value).hexdigest() for name, value in packed.items()},
                code=code,
                retained_excerpt_source=retain.name,
                retained_excerpt_rows=60,
                retained_excerpt_sha256=sha256(sample).hexdigest(),
            )
        ),
    )


def score(report, latitude, longitude):
    locked = json.loads((report / "prediction-lock.json").read_bytes())
    for file, digest in locked["files"].items():
        if sha256((report / file).read_bytes()).hexdigest() != digest:
            raise ValueError(f"prediction receipt differs: {file}")
    config = json.loads(gzip.decompress((report / "config.json.gz").read_bytes()))
    records = json.loads(gzip.decompress((report / "predictions.json.gz").read_bytes()))
    row = int((latitude - LAT_FIRST) // LAT_STEP)
    col = int((longitude - LON_FIRST) // LON_STEP)
    truth = row * TILE_SHAPE[1] + col
    offers = config["offers"][str(truth)]
    sites = config["grid"]
    errors = [distance_km((latitude, longitude), (a, b)) for a, b in sites]
    rows = []
    for record in records:
        for mode, pred in record["modes"].items():
            broad = pred["forced"]
            losses = pred["loss"]
            truth_loss = losses[truth]
            result = dict(
                window=record["window"],
                mode=mode,
                ridges=record["ridges"],
                forced_location=sites[broad] if broad is not None else None,
                forced_error_km=errors[broad] if broad is not None else None,
                true_tile=truth,
                broad_tile=broad,
                broad_correct=broad == truth,
                support=pred["support"],
                margin=pred["margin"],
                best_loss=losses[broad] if broad is not None else None,
                true_tile_loss=truth_loss,
                true_tile_better=sum(loss < truth_loss for loss in losses)
                if broad is not None
                else None,
                early_khz=pred["early_khz"],
                held_khz=pred["held_khz"],
            )
            for condition, offered in offers.items():
                forced = None
                if len({losses[i] for i in offered}) > 1:
                    forced = min(offered, key=losses.__getitem__)
                published = broad in offered and pred["eligible"]
                result[condition] = dict(
                    forced=forced,
                    forced_error_km=errors[forced] if forced is not None else None,
                    published=published,
                    publish_error_km=errors[broad] if published else None,
                )
            rows.append(result)
    preserve(
        report / "scores.json",
        serialize(
            dict(
                site=[latitude, longitude],
                true_cell=truth,
                true_center=sites[truth],
                offers=offers,
                rows=rows,
            )
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("predict")
    run.add_argument("source", type=Path)
    run.add_argument("report", type=Path)
    reveal = commands.add_parser("score")
    reveal.add_argument("report", type=Path)
    reveal.add_argument("latitude", type=float)
    reveal.add_argument("longitude", type=float)
    args = parser.parse_args()
    if args.command == "predict":
        predict(args.source, args.report)
    else:
        score(args.report, args.latitude, args.longitude)


if __name__ == "__main__":
    main()
