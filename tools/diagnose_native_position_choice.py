"""Evaluation-only crossed-site scoring; never supplies truth to regional search."""
import argparse
import math
from pathlib import Path
import struct
import subprocess

from leo.native_pipeline.runner import digest, finite_json, write_json


def site(latitude_deg, longitude_deg, east, north):
    lat0, lon0 = math.radians(latitude_deg), math.radians(longitude_deg)
    angular = math.hypot(east, north) / 6371.0088
    bearing = math.atan2(east, north)
    lat = math.asin(math.sin(lat0)*math.cos(angular) + math.cos(lat0)*math.sin(angular)*math.cos(bearing))
    lon = lon0 + math.atan2(math.sin(bearing)*math.sin(angular)*math.cos(lat0),
                          math.cos(angular)-math.sin(lat0)*math.sin(lat))
    f = 1 / 298.257223563; e2 = f*(2-f)
    radius = 6378.137 / math.sqrt(1-e2*math.sin(lat)**2)
    up = [math.cos(lat)*math.cos(lon), math.cos(lat)*math.sin(lon), math.sin(lat)]
    return [radius*up[0], radius*up[1], radius*(1-e2)*up[2], *up]


def replace_sites(payload, sites):
    header = list(struct.unpack_from('<5I2d', payload))
    if header[0] != 0x31434f4c or len(payload) < 36+48*header[4]:
        raise ValueError('invalid LOC1 header')
    tail = payload[36+48*header[4]:]
    weights = []; offset = 0
    for _ in range(header[3]):
        count, weight = struct.unpack_from('<2I', tail, offset)
        weights.append(weight); offset += 8 + 17*count
    header[4] = len(sites)
    return struct.pack('<5I2d', *header) + b''.join(struct.pack('<6d', *s) for s in sites) + tail, weights


def contribution_rows(points, weights):
    if len(points) != 2 or any(len(p['tracks']) != len(weights) for p in points):
        raise ValueError('score dimensions differ')
    total = sum(weights)
    rows = []
    for index, weight in enumerate(weights):
        a,b = [p['tracks'][index] for p in points]
        delta = weight / total * (min(b['held_hz'],800)**2-min(a['held_hz'],800)**2)
        rows.append({'track_index': index, 'weight_s': weight,
                     'server_site': a, 'arm_site': b,
                     'weighted_mse_delta_arm_minus_server': delta})
    return sorted(rows, key=lambda r: abs(r['weighted_mse_delta_arm_minus_server']), reverse=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--qualification', required=True, type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args(); q = args.qualification
    reference = finite_json(q/'location-authority/server-reference.json')
    prior = next(p for p in reference['priors'] if p['name']=='sacramento')
    region = prior['region']; native = finite_json(q/'regional-exclusive-sacramento-v1/search.json')
    choices = [prior['selected'], native['selected']]
    sites = [site(region['center_latitude_deg'],region['center_longitude_deg'],
                  p['east_km'],p['north_km']) for p in choices]
    args.output.mkdir(parents=True,exist_ok=False)
    receipt = {'scope': 'Crossed-site evaluation only; unchanged tracks, masks and orbits',
               'binary_sha256': digest(args.binary), 'choices': choices, 'comparisons': {}}
    for label, source in [('published',q/'location-authority/published-reference.loc1'),
                          ('arm',q/'exclusive-location-input/tracks.loc1')]:
        blob,weights = replace_sites(source.read_bytes(), sites)
        path = args.output/f'{label}.loc1';path.write_bytes(blob)
        result = subprocess.run([str(args.binary.resolve()),'score',str(path.resolve()),'2'],
                                capture_output=True,text=True,check=True,timeout=60)
        (args.output/f'{label}.json').write_text(result.stdout)
        points = finite_json(args.output/f'{label}.json')['points']
        rows = contribution_rows(points, weights)
        write_json(args.output/f'{label}-contributions.json', rows)
        delta = points[1]['score_hz']**2-points[0]['score_hz']**2
        if not math.isclose(sum(r['weighted_mse_delta_arm_minus_server'] for r in rows),delta,abs_tol=1e-7):
            raise ValueError('track contributions do not reconstruct aggregate')
        receipt['comparisons'][label] = {'input_sha256':digest(source),
            'server_site_score_hz':points[0]['score_hz'], 'arm_site_score_hz':points[1]['score_hz'],
            'weighted_mse_delta_arm_minus_server':delta,
            'tracks_preferring_arm_site':sum(r['weighted_mse_delta_arm_minus_server']<0 for r in rows),
            'tracks_preferring_server_site':sum(r['weighted_mse_delta_arm_minus_server']>0 for r in rows)}
    write_json(args.output/'receipt.json',receipt)
    print(receipt['comparisons'])


if __name__ == '__main__':main()
