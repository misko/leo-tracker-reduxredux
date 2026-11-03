"""Render per-capture replay inputs without reading IQ or changing its authority."""
import argparse
import json
import re
from pathlib import Path, PurePosixPath

from leo.contracts.digests import canonical_digest


def render(capture, capture_digest, analysis_digest, iq_directory, template_directory):
    for value in (capture_digest, analysis_digest):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
            raise ValueError('invalid authority digest')
    if canonical_digest(capture) != capture_digest:
        raise ValueError('capture digest mismatch')
    for directory in (iq_directory, template_directory):
        if not directory.startswith('/') or '..' in PurePosixPath(directory).parts or any(c.isspace() for c in directory):
            raise ValueError('invalid input directory')
    geometry = capture['receipt']['plan']['geometry']
    timing = capture['timing']
    events = capture['receipt']['events']
    if (geometry['sample_rate_hz'] != 2500000 or geometry['receiver_ids'] != [0, 1]
            or timing['sample_rate_hz'] != 2500000 or timing['qualified'] is not True
            or not 1 <= len(events) <= 10000):
        raise ValueError('unsupported or unqualified capture')
    anchor = timing['session_start_device_sample_counter']
    utc = timing['first_sample_estimate_utc_ns']
    width = timing['first_sample_bracket_width_ns']
    if any(type(v) is not int for v in (anchor, utc, width)) or min(anchor, width) < 0 or utc <= 0:
        raise ValueError('invalid capture clock')
    first = events[0]['valid_start_counter']
    generation = events[0]['decision']['generation']
    if type(generation) is not int or generation <= 0:
        raise ValueError('invalid generation')
    manifest, authority = [], []
    previous = -1
    for i, event in enumerate(events):
        start, end = event['valid_start_counter'], event['valid_end_counter_exclusive']
        if (event['visit_index'] != i or type(start) is not int or type(end) is not int
                or start < anchor or start < previous or end-start != 300000
                or event['decision']['generation'] != generation):
            raise ValueError('invalid visit continuity or dwell')
        offset = (start-first)*400
        if offset > 1200000000000:
            raise ValueError('unsupported capture duration')
        previous = end
        target = event['target']
        edge, channel = target['edge'], target['channel']
        rf = target['rf_center_hz']-event['actual_if_offset_hz']
        if edge not in ('lower', 'upper') or type(channel) is not int or not 1 <= channel <= 4 or type(rf) is not int or rf <= 0:
            raise ValueError('invalid receiver lane')
        manifest.append('\t'.join(map(str, [i, offset,
            f'{template_directory}/{edge}-exact.c128',
            f'{template_directory}/{edge}-control.c128',
            f'{iq_directory}/visit-{i:06d}.ci16'])))
        authority.append('\t'.join(map(str, [2500000, anchor, utc, generation, i,
            start, 0, 0, channel, int(edge == 'upper'), rf, width,
            capture_digest, analysis_digest, 1])))
    return '\n'.join(manifest)+'\n', '\n'.join(authority)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--capture-digest', required=True)
    parser.add_argument('--analysis-digest', required=True)
    parser.add_argument('--iq-directory', required=True)
    parser.add_argument('--template-directory', required=True)
    args = parser.parse_args()
    manifest, authority = render(json.loads(args.capture.read_text()), args.capture_digest,
        args.analysis_digest, args.iq_directory, args.template_directory)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'manifest.tsv').write_text(manifest)
    (args.output/'authority.tsv').write_text(authority)


if __name__ == '__main__':
    main()
