"""Prepare the sealed field cohort from a local copy of StarLoc's release."""

import argparse
import collections
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import itertools
import json
from math import cos, pi, radians, sin
from pathlib import Path
import random
import secrets

import numpy as np
from scipy.io import loadmat


DURATION_S = 900
RADIO_HZ = 11_325_000_000
CHANNEL = 3
FFT_BIN_HZ = 2_000_000 / 28_000
HARMONIC_HZ = 43_945.5
METRES_PER_DEGREE = 111_195.08
SITE_GROUP_DISTANCE_M = 500
SOURCE = 'https://github.com/GiddaZhang/Starloc/tree/fc010f950dfac5ac6d7a345db24513217fbb81d5'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(data):
    return (json.dumps(data, separators=(',', ':'), allow_nan=False, sort_keys=True) + '\n').encode()


def offset_limited(latlon, east_km, north_km):
    lat, lon = latlon
    return [round(lat + north_km * 1000 / METRES_PER_DEGREE, 8),
            round(lon + east_km * 1000 / (METRES_PER_DEGREE * cos(radians(lat))), 8)]


def local_distance(latlon, coordinates):
    meters = (np.asarray(coordinates) - latlon) * METRES_PER_DEGREE
    meters[..., 1] *= cos(radians(latlon[0]))
    return np.linalg.norm(meters, axis=-1)


def parse_gnss_time(text, anchor_dt):
    text = text.split(': ', 1)[1].strip()
    if len(text.split()) == 4:
        return datetime.strptime(text, '%H:%M:%S %b %d %Y').replace(tzinfo=timezone.utc)
    return datetime.strptime(f'{anchor_dt.year} {text}', '%Y %d %b %H:%M:%S').replace(tzinfo=timezone.utc)


def read_site(source_dir, imu, anchor_ns, tracks):
    chunks = sorted((source_dir / 'data' / Path(imu).parent).glob(Path(imu).name + '.*.part'))
    anchor_dt = datetime.fromtimestamp(anchor_ns // 10**9, tz=timezone.utc)
    fixes = []
    for chunk in chunks:
        for row in chunk.read_text().splitlines()[1:-1]:
            fields = row.split('|')
            if len(fields) != 6:
                continue
            t = (parse_gnss_time(fields[0], anchor_dt).timestamp() - anchor_ns / 10**9)
            values = [float(value.split(': ', 1)[1]) for value in fields[3].split(',') + [fields[4]]]
            if 0 <= t <= DURATION_S and np.isfinite(values).all():
                fixes.append([t, *values])
    if not fixes:
        raise ValueError(f'No in-capture GNSS in {imu}')
    fixes = np.asarray(fixes)
    latlon = np.median(fixes[:, 1:3], axis=0)
    max_motion_m = float(np.max(local_distance(latlon, fixes[:, 1:3])))
    if max_motion_m > 30 or min(fixes[:, 0]) > 30 or max(fixes[:, 0]) < 820:
        raise ValueError(f'Insufficient stationary GNSS coverage in {imu}')
    return latlon.tolist(), {
        'imu_path': imu, 'gnss_points': len(fixes), 'gnss_first_s': min(fixes[:, 0]),
        'gnss_last_s': max(fixes[:, 0]), 'max_gnss_spread_from_median_m': max_motion_m,
        'altitude_median_m': float(np.median(fixes[:, 3])),
        'seconds_from_last_gnss_to_last_measurement': max(0.0, max(t[-1] for t, _ in tracks) - max(fixes[:, 0])),
        'gnss_chunk_sha256': {path.name: digest(path.read_bytes()) for path in chunks},
    }


def read_tracks(path):
    windows = loadmat(path, variable_names=['main_tone_dict'])['main_tone_dict'].ravel()
    tracks = []
    for window in windows:
        points = window[:, :2].real
        points = points[np.argsort(points[:, 0])]
        values = points[:, 1]
        times, starts, counts = np.unique(points[:, 0], return_index=True, return_counts=True)
        if not np.isfinite(points).all() or len(times) < 5 or times[0] < 0 or times[-1] >= DURATION_S:
            raise ValueError(f'Unexpected measurement range in {path}')
        median_by_time = np.asarray([np.median(values[s:s + n]) for s, n in zip(starts, counts)])

        # Take an actual timestamp near each half-second bin's temporal median.
        _, half_second_starts, half_second_counts = np.unique(
            np.floor(times * 2).astype(int), return_index=True, return_counts=True)
        pick = half_second_starts + (half_second_counts - 1) // 2
        tracks.append((times[pick], median_by_time[pick]))

    # Compare measured trajectories alone. Keep the longer of suspected simultaneous
    # copies if an integer beacon-tone spacing makes them nearly identical.
    duplicates = []
    for (ia, (ta, fa)), (ib, (tb, fb)) in itertools.combinations(enumerate(tracks), 2):
        lo = max(ta[0], tb[0])
        hi = min(ta[-1], tb[-1])
        if hi - lo < 5:
            continue
        grid = np.arange(lo, hi, .5)
        if np.any(np.diff(ta[(ta >= lo) & (ta <= hi)]) > 2) or np.any(np.diff(tb[(tb >= lo) & (tb <= hi)]) > 2):
            continue
        delta = np.interp(grid, ta, fa) - np.interp(grid, tb, fb)
        harmonic = round(np.median(delta) / HARMONIC_HZ)
        centered = delta - np.median(delta)
        if np.median(np.abs(delta - harmonic * HARMONIC_HZ)) <= 25 * FFT_BIN_HZ and np.median(np.abs(centered)) <= 7 * FFT_BIN_HZ:
            chosen, removed = (ia, ib) if ta[-1] - ta[0] >= tb[-1] - tb[0] else (ib, ia)
            duplicates.append({'retained': chosen + 1, 'removed': removed + 1, 'difference_harmonics': harmonic})
    remove = {item['removed'] - 1 for item in duplicates}
    return [track for i, track in enumerate(tracks) if i not in remove], duplicates


def parse_catalog(path):
    raw = path.read_bytes()
    lines = raw.decode('ascii').splitlines()
    if len(lines) % 3:
        raise ValueError(f'Expected name plus TLE pairs in {path}')
    result = []
    for name, first, second in zip(lines[::3], lines[1::3], lines[2::3]):
        norad = first[2:7]
        if not first.startswith('1 ') or not second.startswith('2 ') or second[2:7] != norad:
            raise ValueError(f'Bad TLE record in {path}')
        year = 2000 + int(first[18:20])
        jan = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()) * 10**9
        epoch = jan + int((Decimal(first[20:32]) - 1) * 86_400 * 10**9)
        result.append((norad, epoch, (name.rstrip(), first.rstrip(), second.rstrip())))
    return result, digest(raw)


def orbit_for(anchor, available):
    elements = {}
    future_count = 0
    for _, records in available:
        for norad, epoch, lines in records:
            if epoch > anchor:
                future_count += 1
                continue
            if norad not in elements or epoch >= elements[norad][0]:
                elements[norad] = (epoch, lines)
    tle = '\n'.join(line for norad in sorted(elements) for line in elements[norad][1]) + '\n'
    return tle.encode(), {'orbit_rows': len(elements), 'excluded_future_rows_seen': future_count,
                          'max_retained_element_epoch_ns': max(epoch for epoch, _ in elements.values())}


def match_group(latlon, known_groups):
    for group, coordinates in known_groups.items():
        if local_distance(latlon, coordinates) <= SITE_GROUP_DISTANCE_M:
            return group
    group = f'field-site-{len(known_groups) + 1:02d}'
    known_groups[group] = latlon
    return group


def opaque_id(rng, prefix):
    return f'{prefix}-{rng.getrandbits(96):024x}'


def paired_offers(rng, latlon, difficulty):
    spacing = (37, 60) if difficulty == 'near' else (60, 150)
    angle = rng.uniform(0, 2 * pi)
    a, b = rng.uniform(*spacing), rng.uniform(*spacing)
    x = np.asarray([cos(angle), sin(angle)]) * a
    y = np.asarray([-sin(angle), cos(angle)]) * b
    corner = rng.choice([-1, 1]), rng.choice([-1, 1])
    x, y = x * corner[0], y * corner[1]
    base = np.asarray([rng.uniform(-9, 9), rng.uniform(-9, 9)])

    if rng.randrange(2):
        x, y = y, x

    def region(offset):
        return {'id': opaque_id(rng, 'region'), 'center': offset_limited(latlon, *offset)}

    true_region = region(base)
    shared = [region(base + x), region(base + x + y)]
    present = shared + [true_region, region(base + y)]
    missing = shared + [region(base + 2 * x), region(base + 2 * x + y)]
    for offers in (present, missing):
        rng.shuffle(offers)
        for first, second in itertools.combinations(offers, 2):
            a = np.asarray(first['center'])
            b = np.asarray(second['center'])
            delta = np.abs(a - b) * METRES_PER_DEGREE
            delta[1] *= cos(radians(latlon[0]))
            if max(delta) <= 25_000:
                raise AssertionError('Offered squares overlap')
    return true_region['id'], present, missing


def run(source_dir, output, seed):
    configs = json.loads((source_dir / 'configs.json').read_text())
    configs.sort(key=lambda case: Decimal(case['start']))
    rng = random.Random(seed)
    known_groups = {}
    available = []
    public = output / 'public_field'
    private = output / 'field_private'
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in ('queries', 'observations', 'orbits'):
        (public / directory).mkdir(parents=True, exist_ok=True)
    provenance = []
    truth = []
    query_ids = []
    for record in configs:
        anchor = int(Decimal(record['start']) * 10**9)
        source = source_dir / 'data' / record['key']
        catalog, catalog_digest = parse_catalog(source / 'Starlink.tle')
        if catalog_digest not in {key for key, _ in available}:
            available.append((catalog_digest, catalog))
        tle, tle_stats = orbit_for(anchor, available)
        catalog_id = digest(tle)
        (public / 'orbits' / f'{catalog_id}.tle').write_bytes(tle)

        tone_path = source / 'tracked_tones.mat'
        tracks, duplicates = read_tracks(tone_path)
        latlon, site_metadata = read_site(source_dir, record['imu'], anchor, tracks)
        obs = {'anchor_utc_ns': anchor, 'cutoff_utc_ns': anchor, 'catalog_timestamp_ns': anchor,
               'duration_s': DURATION_S, 'tracks': [
                   {'times': np.round(times, 8).tolist(), 'values': np.round(hz, 6).tolist(),
                    'receiver': 1, 'channel': CHANNEL, 'rf_hz': RADIO_HZ}
                   for times, hz in tracks]}
        obs_bytes = json_bytes(obs)
        obs_id = digest(obs_bytes)
        (public / 'observations' / f'{obs_id}.json').write_bytes(obs_bytes)

        group = match_group(latlon, known_groups)
        difficulty = 'near' if len(provenance) % 2 == 0 else 'regional'
        true_region, present, missing = paired_offers(rng, latlon, difficulty)
        pair_id = opaque_id(rng, 'field-pair')
        for condition, offers in [('present', present), ('missing', missing)]:
            query_id = opaque_id(rng, 'field-query')
            query_ids.append(query_id)
            query = {'id': query_id, 'observation': obs_id, 'catalog': catalog_id, 'regions': offers}
            (public / 'queries' / f'{query_id}.json').write_bytes(json_bytes(query))
            truth.append({'id': query_id, 'pair': pair_id, 'site_group': group, 'source': 'field',
                          'condition': condition, 'true_region': true_region if condition == 'present' else None,
                          'latlon': latlon, 'difficulty': difficulty})
        provenance.append({'pair': pair_id, 'date': record['key'], 'start': record['start'],
                           'site_group': group, 'track_file_sha256': digest(tone_path.read_bytes()),
                           'orbit_file_sha256': catalog_digest, 'duplicates': duplicates,
                           'track_count': len(tracks), 'early_tracks': sum(bool(t[-1] <= 450) for t, _ in tracks),
                           'late_tracks': sum(bool(t[0] >= 450) for t, _ in tracks),
                           'catalog_sources_available': list(dict.fromkeys(value for value, _ in available)),
                           **tle_stats, **site_metadata})

    rng.shuffle(query_ids)
    rng.shuffle(truth)
    manifest = json_bytes({'queries': query_ids})
    (private / 'truth.json').write_bytes(json_bytes({'cases': truth}))
    (private / 'source_provenance.json').write_bytes(json_bytes({'source': SOURCE, 'captures': provenance, 'seed': seed}))
    for file in private.glob('*.json'):
        file.chmod(0o600)
    (public / 'manifest.json').write_bytes(manifest)
    receipt = {'status': 'ready', 'field_captures': len(provenance), 'physical_site_groups': len(known_groups),
               'region_scale_groups': len({row['difficulty'] for row in truth}),
               'query_counts': dict(collections.Counter(row['condition'] for row in truth)),
               'track_count_total': sum(row['track_count'] for row in provenance),
               'track_count_range': [min(row['track_count'] for row in provenance), max(row['track_count'] for row in provenance)],
               'public_manifest_sha256': digest(manifest),
               'public_query_sha256': {query: digest((public / 'queries' / f'{query}.json').read_bytes()) for query in query_ids},
               'sealed_truth_sha256': digest((private / 'truth.json').read_bytes()),
               'public_source_annotation': 'Measured single-channel Ku-band beacon frequency tracks, externally windowed before export. '
                                           'Frequency and time are preserved from the measured track arrays. '
                                           'Capture-time catalog availability is documented by the source without an independent retrieval timestamp.'}
    (output / 'field-receipt.json').write_bytes(json_bytes(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_dir', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seed', type=int, default=secrets.randbits(64))
    arguments = parser.parse_args()
    run(arguments.source_dir, arguments.output, arguments.seed)
