"""Render a bounded sequential ARM diagnostic job from pinned stage commands."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shlex


def render(plan, payloads):
    directory = plan['output_directory']
    path = PurePosixPath(directory)
    if not path.is_absolute() or '..' in path.parts or not directory.startswith('/mnt/glrtbench/'):
        raise ValueError('invalid output directory')
    stages = plan['stages']
    if not 1 <= len(stages) <= 8:
        raise ValueError('invalid stage count')
    names = set()
    lines = ['#!/bin/sh', 'set -eu', 'set -C', 'umask 077', 'mkdir ' + shlex.quote(directory)]
    for stage in stages:
        name, argv, timeout = stage['name'], stage['argv'], stage['timeout_s']
        if not re.fullmatch('[a-z][a-z0-9_]*', name) or name in names:
            raise ValueError('invalid or duplicate stage name')
        names.add(name)
        if type(timeout) is not int or not 1 <= timeout <= 600:
            raise ValueError('invalid stage timeout')
        if not argv or argv[0] not in payloads or not all(
                isinstance(x, str) and x and '\0' not in x for x in argv):
            raise ValueError('stage command must be pinned with explicit arguments')
        command = ['/mnt/glrtbench/native-adaptive/current/measure-run', str(timeout), *argv]
        lines.append(shlex.join(command) + ' > ' + shlex.quote(directory + '/' + name + '.stdout')
                     + ' 2> ' + shlex.quote(directory + '/' + name + '.stderr'))
    # Only a successful complete chain publishes the last stage's stdout.
    lines.append('cat ' + shlex.quote(directory + '/' + stages[-1]['name'] + '.stdout'))
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('protocol', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    with args.output.open('x') as output:
        output.write(render(protocol['chain'], protocol['payloads']))


if __name__ == '__main__':
    main()
