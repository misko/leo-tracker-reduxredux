"""Freeze a known-installation measured RF control from official DS29 inputs."""

import argparse
import hashlib
import hmac
import json
import math
import os
import random
import secrets
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np


PRIVATE = Path(__file__).resolve().parent
BASE = PRIVATE.parent
ROOT = BASE.parents[1]
DS29 = Path('/srv/bulk/leo-dev/ds29-20261113')
SNAPSHOT = DS29 / 'snapshot'
RANK_DOMAIN = b'2026-11-18-blind-regional-receiver/DS29/recorded-selection/v1\x00'
GRAPH_CONFIG = ROOT / 'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json'
sys.path.insert(0, str(ROOT / 'tools'))
from evaluate_ds22_merged_tracks import graph_tracks, winners
from leo.analysis.polynomial_tracklets import TrackConfig


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(document):
    return (json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def load(path):
    return json.loads(path.read_bytes())


def write(path, document):
    with path.open('xb') as stream:
        stream.write(encoded(document))


def select():
    membership_path = DS29 / 'dataset/membership-summary.json'
    inventory_path = SNAPSHOT / 'inventory.json'
    membership_bytes, inventory_bytes = membership_path.read_bytes(), inventory_path.read_bytes()
    membership, inventory = json.loads(membership_bytes), json.loads(inventory_bytes)
    seal = load(DS29 / 'dataset/seal.json')['files']
    assert seal['membership-summary.json'] == 'sha256:' + sha(membership_bytes)
    assert seal['manifest.json'] == membership['manifest_sha256'] == inventory['dataset_manifest_sha256']
    snapshot_members = {r['dataset_label']: r for r in inventory['members']}
    fast = sorted((r for r in membership['members'] if r['mode'] == 'fast'),
                  key=lambda r: (r['captured_utc_ns'], r['dataset_label']))
    chosen, strata = [], []
    for quartile in range(4):
        members = fast[len(fast) * quartile // 4:len(fast) * (quartile + 1) // 4]
        for band in ('lower', 'upper'):
            eligible = []
            for member in members:
                label = member['dataset_label']
                bound = snapshot_members[label]
                assert all(member[k] == bound[k] for k in ('recording_id', 'session_id', 'captured_utc_ns'))
                if (member['recording_id'].endswith('-' + band)
                        and member['recording_state'] == 'complete'
                        and member['glrt_availability']['available']
                        and bound['availability'] == 'available' and bound['causal_snapshots']):
                    rank = sha(RANK_DOMAIN + member['raw_identity_sha256'].encode('ascii'))
                    eligible.append((rank, label, member, bound))
            rank, label, member, bound = min(eligible)
            chosen.append(dict(quartile=quartile + 1, band=band, rank_sha256=rank,
                               member=member, source=bound))
            strata.append(dict(quartile=quartile + 1, band=band, eligible=len(eligible)))
    protocol = dict(
        dataset_manifest_sha256=seal['manifest.json'], official_membership_path=str(membership_path),
        official_membership_sha256=sha(membership_bytes), snapshot_inventory_path=str(inventory_path),
        snapshot_inventory_sha256=sha(inventory_bytes), rank_domain_hex=RANK_DOMAIN.hex(),
        selection_method='Chronological quartiles of all official fast members. In each quartile and explicit lower/upper band, choose the available complete member with the lowest domain-separated SHA-256 of its sealed raw identity.',
        selected_before_track_construction=True, numerical_outcomes_consulted=False,
        selection_utc=datetime.now(timezone.utc).isoformat(), strata=strata, chosen=chosen,
        query_seed_hex=secrets.token_hex(32),
    )
    write(PRIVATE / 'selection.json', protocol)
    return len(chosen)


def observation(selection):
    source = selection['source']
    native_path = Path(source['frozen_native_path'])
    native_bytes = native_path.read_bytes()
    assert source['input_sha256'] == 'sha256:' + sha(native_bytes)
    native = json.loads(native_bytes)
    assert native['source']['session_id'] == source['session_id']
    rows, metadata = winners(native)
    config = TrackConfig(**load(GRAPH_CONFIG)['config'])
    anonymous, assigned = graph_tracks(rows, 'anonymous', config)
    tracks = [dict(times=t['times'].tolist(), values=t['values'].tolist(), rf_hz=t['rf_hz'],
                   receiver=t['receiver'], channel=t['channel']) for t in anonymous]
    cutoff = metadata['causal_cutoff_utc_ns']
    assert cutoff == source['cutoff_utc_ns'] <= source['captured_utc_ns']
    preceding = [(int(name.split('-', 1)[0]), name, digest)
                 for name, digest in source['causal_snapshots'].items()
                 if int(name.split('-', 1)[0]) < cutoff]
    catalogue_ns, catalogue_name, digest = max(preceding)
    catalogue_path = native_path.parent / 'tle/archive/space-track' / catalogue_name
    catalogue = catalogue_path.read_bytes()
    assert digest == sha(catalogue) and catalogue_name == f'{catalogue_ns}-{digest}.tle'
    observed = dict(anchor_utc_ns=metadata['anchor_utc_ns'], cutoff_utc_ns=cutoff,
                    catalog_timestamp_ns=catalogue_ns, duration_s=metadata['duration_s'], tracks=tracks)
    audit = dict(dataset_label=source['dataset_label'], native_path=str(native_path),
                 native_sha256=source['input_sha256'], catalogue_path=str(catalogue_path),
                 catalogue_sha256=digest, anchor_utc_ns=metadata['anchor_utc_ns'],
                 capture_start_utc_ns=source['captured_utc_ns'], cutoff_utc_ns=cutoff,
                 catalog_timestamp_ns=catalogue_ns, clock_half_width_s=metadata['utc_half_width_s'],
                 winners=len(rows), assigned=assigned, tracks=len(tracks),
                 graph_quality_counts=dict(Counter(t['quality_status'] for t in anonymous)))
    return observed, catalogue, audit


def center(latlon, east, north):
    lat, lon = map(math.radians, latlon)
    arc, angle = math.hypot(east, north) / 6371.0088, math.atan2(east, north)
    new_lat = math.asin(math.sin(lat) * math.cos(arc) + math.cos(lat) * math.sin(arc) * math.cos(angle))
    dlon = math.atan2(math.sin(angle) * math.sin(arc) * math.cos(lat), math.cos(arc) - math.sin(lat) * math.sin(new_lat))
    return [math.degrees(new_lat), (math.degrees(lon + dlon) + 180) % 360 - 180]


def local_offset(center_latlon, target):
    lat0, lon0 = map(math.radians, center_latlon)
    lat, lon = map(math.radians, target)
    angular = 2 * math.asin(math.sqrt(math.sin((lat - lat0) / 2)**2
                                    + math.cos(lat0) * math.cos(lat) * math.sin((lon - lon0) / 2)**2))
    azimuth = math.atan2(math.sin(lon - lon0) * math.cos(lat),
                        math.cos(lat0) * math.sin(lat) - math.sin(lat0) * math.cos(lat) * math.cos(lon - lon0))
    return 6371.0088 * angular * math.sin(azimuth), 6371.0088 * angular * math.cos(azimuth)


def queries(seed, roster, latlon):
    def opaque(namespace):
        return hmac.new(seed, namespace.encode('ascii'), hashlib.sha256).hexdigest()[:32]

    rng = random.Random(int.from_bytes(seed, 'big'))
    near_missing = set(rng.sample(range(len(roster)), len(roster) // 2))
    cases, entries = [], []
    for i, (obs, cat) in enumerate(roster):
        pair = opaque(f'pair/{i}')
        for present in (True, False):
            qid = opaque(f'query/{i}/{present}')
            positions = []
            if present:
                while True:
                    east, north = rng.uniform(-10, 10), rng.uniform(-10, 10)
                    if math.hypot(east, north) >= 2:
                        break
                positions.append(center(latlon, east, north))
            near = 2 if present else (3 if i in near_missing else 0)
            for is_near in [True] * near + [False] * (4 - near - int(present)):
                while True:
                    radius = rng.uniform(26, 65) if is_near else rng.uniform(250, 950)
                    azimuth = rng.uniform(0, 2 * math.pi)
                    point = center(latlon, radius * math.sin(azimuth), radius * math.cos(azimuth))
                    if all(math.hypot(*local_offset(p, point)) >= 25 for p in positions):
                        positions.append(point)
                        break
            regions = [dict(id=opaque(f'region/{qid}/{j}'), center=p) for j, p in enumerate(positions)]
            true_region = regions[0]['id'] if present else None
            rng.shuffle(regions)
            entries.append(dict(id=qid, observation=obs, catalog=cat, regions=regions))
            cases.append(dict(id=qid, pair=pair, site_group='known-ds26-ds29-installation',
                              source='known_site_control', condition='present' if present else 'missing',
                              true_region=true_region, latlon=latlon,
                              difficulty='mixed' if present else ('near' if i in near_missing else 'remote')))
    rng.shuffle(entries)
    return entries, dict(cases=sorted(cases, key=lambda c: c['id']))


def verify(public, truth):
    manifest = load(public / 'manifest.json')['queries']
    by_id = {r['id']: r for r in truth['cases']}
    assert len(manifest) == len(set(manifest)) == len(by_id) == 16 and set(manifest) == set(by_id)
    pair_queries = {}
    checked_observations = set()
    checked_catalogues = set()
    for qid in manifest:
        query = load(public / 'queries' / f'{qid}.json')
        label = by_id[qid]
        assert qid == query['id']
        assert set(query) == {'id', 'observation', 'catalog', 'regions'}
        assert len(query['regions']) == len({r['id'] for r in query['regions']}) == 4
        included = [r['id'] for r in query['regions']
                    if max(map(abs, local_offset(r['center'], label['latlon']))) < 12.5]
        assert included == ([label['true_region']] if label['condition'] == 'present' else [])
        pair_queries.setdefault(label['pair'], []).append((label['condition'], query['observation'], query['catalog']))
        if query['catalog'] not in checked_catalogues:
            catalogue = (public / 'orbits' / f"{query['catalog']}.tle").read_bytes()
            assert sha(catalogue) == query['catalog']
            lines = catalogue.decode('ascii').splitlines()
            assert len(lines) % 3 == 0 and len(lines) > 300
            assert all(line.startswith(f'{i % 3} ') for i, line in enumerate(lines))
            checked_catalogues.add(query['catalog'])
        if query['observation'] not in checked_observations:
            payload = (public / 'observations' / f"{query['observation']}.json").read_bytes()
            assert sha(payload) == query['observation']
            observed = json.loads(payload)
            assert observed['catalog_timestamp_ns'] < observed['cutoff_utc_ns'] <= observed['anchor_utc_ns']
            assert observed['tracks'] and observed['duration_s'] > 0
            for track in observed['tracks']:
                assert track['receiver'] in (1, 2) and track['channel'] in range(1, 9) and track['rf_hz'] > 0
                assert len(track['times']) == len(track['values']) >= 8
                assert 0 <= track['times'][0] < track['times'][-1] <= observed['duration_s']
                assert np.all(np.diff(track['times']) > 0) and np.all(np.isfinite(track['values']))
            checked_observations.add(query['observation'])
    assert len(pair_queries) == len(checked_observations) == 8
    assert all(len(z) == 2 and {r[0] for r in z} == {'present', 'missing'} and z[0][1:] == z[1][1:]
               for z in pair_queries.values())
    return dict(queries=len(manifest), observations=len(checked_observations),
                catalogues=len(checked_catalogues), site_groups=1)


def prepare(workers):
    protocol = load(PRIVATE / 'selection.json')
    seed = bytes.fromhex(protocol['query_seed_hex'])
    if (BASE / 'public_recorded').exists() or (BASE / 'recorded-receipt.json').exists():
        raise FileExistsError('Recorded delivery is already present')
    site_path = SNAPSHOT / 'site-authority.json'
    site = load(site_path)
    site_audit_path = SNAPSHOT / 'site-audit.json'
    site_audit = load(site_audit_path)
    assert site_audit['authority_sha256'] == 'sha256:' + sha(site_path.read_bytes())
    eligible = {row['dataset_label'] for row in site_audit['members'] if row['authority_eligible']}
    assert all(row['member']['dataset_label'] in eligible for row in protocol['chosen'])
    coords = [site['latitude_deg'], site['longitude_deg']]
    with TemporaryDirectory(dir=BASE, prefix='.recorded-build-') as temp:
        public = Path(temp) / 'public_recorded'
        for name in ('queries', 'observations', 'orbits'):
            (public / name).mkdir(parents=True)
        roster, provenance = [], []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for observed, catalogue, audit in pool.map(observation, protocol['chosen']):
                payload = encoded(observed)
                obs, cat = sha(payload), sha(catalogue)
                (public / 'observations' / f'{obs}.json').write_bytes(payload)
                (public / 'orbits' / f'{cat}.tle').write_bytes(catalogue)
                roster.append((obs, cat))
                provenance.append(dict(audit, observation_sha256=obs))
        entries, truth = queries(seed, roster, coords)
        for entry in entries:
            write(public / 'queries' / f"{entry['id']}.json", entry)
        write(public / 'manifest.json', dict(queries=[entry['id'] for entry in entries]))
        counts = verify(public, truth)
        code_paths = [Path(__file__), ROOT / 'tools/evaluate_ds22_merged_tracks.py', GRAPH_CONFIG]
        code_paths.extend(ROOT / 'src/leo/analysis' / f'{n}.py' for n in
                          ('graph_tracklets', 'polynomial_tracklets', 'tracklet_fitting', 'glrt_frequency_input'))
        write(PRIVATE / 'truth.json', truth)
        write(PRIVATE / 'provenance.json', dict(
            evidence_scope='Measured RF at one previously known DS26/DS29 installation. This is a regional receiver control. The experiment does not score coordinates or measure transfer to a new physical site.',
            prior_trace_exposure='The native evidence is archived DS29 input and may have been used in historical DS29 runs. The selection and track construction here do not use their solver outputs.',
            track_policy='Previous DS22 chronological Graph policy and frozen Graph settings, fit independently by receiver and actual channel. Each value is the selected native fractional CFO in Hz plus the Graph integer alias lift, with an unknown whole-track branch. No smoothing, synthetic interpolation, orbital identity, or station position enters the track construction.',
            graph_alias_spacing_hz=load(GRAPH_CONFIG)['config']['alias_spacing_hz'],
            catalogue_policy='Latest strictly pre-cutoff unmodified raw Space-Track snapshot from the prior DS29 freezer, bytes checked against its archive receipt.',
            timing_policy='Sample-counter probe midpoint seconds from the native capture anchor. UTC anchor is its realtime-bracket midpoint. Cutoff is the earlier bracket endpoint.',
            region_policy='25 km square tiles. Positive positions jittered independently by up to 10 km per axis. Near centers 26 to 65 km away and far centers 250 to 950 km away. Three near centers and one far in near-missing controls. Four far centers in remote-missing controls. Hypothesis centers are sampled afresh for each query.',
            site_authority=dict(path=str(site_path), sha256=sha(site_path.read_bytes()),
                                eligibility_path=str(site_audit_path), eligibility_sha256=sha(site_audit_path.read_bytes())),
            implementation_sha256={str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in code_paths},
            observations=provenance))
        public_hashes = {str(p.relative_to(public)): sha(p.read_bytes()) for p in sorted(public.rglob('*')) if p.is_file()}
        private_hashes = {p.name: sha(p.read_bytes()) for p in sorted(PRIVATE.iterdir()) if p.is_file()}
        receipt = dict(scope='measured RF control at one previously known physical installation',
                       status='ready', counts=counts, hash_algorithm='SHA-256',
                       public_tree_sha256=sha(encoded(public_hashes)), public_files_sha256=public_hashes,
                       private_tree_sha256=sha(encoded(private_hashes)), private_files_sha256=private_hashes)
        os.replace(public, BASE / public.name)
        write(BASE / 'recorded-receipt.json', receipt)
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('select', 'prepare', 'verify'))
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    if args.stage == 'select':
        print(json.dumps(dict(selection_frozen=select())))
    elif args.stage == 'prepare':
        print(json.dumps(prepare(args.workers)))
    else:
        print(json.dumps(verify(BASE / 'public_recorded', load(PRIVATE / 'truth.json'))))
