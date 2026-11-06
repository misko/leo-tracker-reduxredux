"""External read-only process-tree sampler; stop if the bound owner exits."""

import argparse
import json
import time
from pathlib import Path


def record(pid):
    try:
        text = (Path('/proc') / str(pid) / 'stat').read_text()
        fields = text[text.rindex(')') + 2:].split()
        return dict(pid=int(pid), state=fields[0], parent=int(fields[1]),
                    start_ticks=int(fields[19]), cpu_ticks=int(fields[11]) + int(fields[12]),
                    minor_faults=int(fields[7]), major_faults=int(fields[9]),
                    rss_pages=int(fields[21]))
    except (FileNotFoundError, ProcessLookupError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    initial = record(args.pid)
    if initial is None:
        raise ValueError('Owner is not alive')
    with args.output.open('x') as stream:
        while True:
            owner = record(args.pid)
            if owner is None or owner['start_ticks'] != initial['start_ticks']:
                return
            rows = [r for p in Path('/proc').iterdir() if p.name.isdigit()
                    if (r := record(int(p.name))) is not None]
            selected = {args.pid}
            while True:
                expanded = selected | {r['pid'] for r in rows if r['parent'] in selected}
                if expanded == selected:
                    break
                selected = expanded
            value = dict(monotonic=time.perf_counter(),
                         processes=[r for r in rows if r['pid'] in selected],
                         cpu_pressure=Path('/proc/pressure/cpu').read_text(),
                         memory_pressure=Path('/proc/pressure/memory').read_text())
            stream.write(json.dumps(value) + '\n')
            stream.flush()
            time.sleep(1)


if __name__ == '__main__':
    main()
