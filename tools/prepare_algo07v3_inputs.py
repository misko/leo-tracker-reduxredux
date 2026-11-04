"""Prepare v3 native/causal inputs independently; does not estimate a position."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3.elements import ElementParser
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.application.localization_v3 import prepare_native_scan
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def write(path, value):
    def default(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(type(item).__name__)

    with path.open('x') as stream:
        json.dump(value, stream, default=default, allow_nan=False, sort_keys=True)
        stream.write('\n')


def run(args):
    native = args.native_input.read_bytes()
    if 'sha256:' + hashlib.sha256(native).hexdigest() != args.input_sha256:
        raise ValueError('Native input differs from declared identity')
    config_bytes = args.track_config.read_bytes()
    config = TrackConfig(**json.loads(config_bytes)['config'])
    output = args.output.resolve()
    if output.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read only')
    output.mkdir(parents=True, exist_ok=False)
    write(output/'launch.json', dict(input_sha256=args.input_sha256,
                                    track_config_sha256=hashlib.sha256(config_bytes).hexdigest(),
                                    screen_center=[args.screen_latitude, args.screen_longitude],
                                    catalogue_root=str(args.tle_root), position_estimated=False))
    element_parser = (parse_element_sets if getattr(args, 'no_element_cache', False)
                      else ElementParser())
    began = time.monotonic()
    prepared = prepare_native_scan(json.loads(native), TleArchiveReader(args.tle_root), config,
                                    screen_latitude_deg=args.screen_latitude,
                                    screen_longitude_deg=args.screen_longitude,
                                    element_parser=element_parser)
    write(output/'tracks.json', prepared['tracks'])
    if prepared['sky'] is not None:
        sky = prepared['sky']
        np.savez_compressed(output/'bank.npz', **sky['bank'])
        write(output/'radio_noise.json', prepared['noise'])
        for name in ('selected_tle', 'previous_tle', 'genuine_previous_tle'):
            with (output/(name.removesuffix('_tle')+'.tle')).open('x') as stream:
                stream.write(sky[name])
        for name in ('nominal_elements', 'previous_receipt',
                     'genuine_previous_receipt', 'metadata'):
            write(output/(name+'.json'), sky[name])
        write(output/'phase_history.json', prepared['phase_history'])
        write(output/'phase_forecast.json', dict(prepared['phase_forecast'],
              history_sha256=hashlib.sha256((output/'phase_history.json').read_bytes()).hexdigest()))
    if args.native_input.read_bytes() != native or args.track_config.read_bytes() != config_bytes:
        raise ValueError('Inputs changed during preparation')
    summary = dict(status=prepared['status'], elapsed_seconds=time.monotonic()-began,
                   element_cache=(element_parser.statistics()
                                  if isinstance(element_parser, ElementParser) else None),
                   position_estimated=False, input_sha256=args.input_sha256,
                   points=len(prepared['tracks']['observations']),
                   tracks=len(prepared['tracks']['tracks']),
                   source_files={str(p.relative_to(output)):
                                 hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(output.iterdir()) if p.is_file()})
    write(output/'summary.json', summary)
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('native-input', 'track-config', 'tle-root', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--input-sha256', required=True)
    parser.add_argument('--screen-latitude', type=float, required=True)
    parser.add_argument('--screen-longitude', type=float, required=True)
    parser.add_argument('--no-element-cache', action='store_true',
                        help='Use the uncached parser for controlled preparation benchmarks')
    raise SystemExit(run(parser.parse_args()))
