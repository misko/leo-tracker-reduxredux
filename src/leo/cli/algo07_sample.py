"""Bounded external sampling of a private benchmark child, without injecting code."""

import re
import subprocess
from pathlib import Path

from leo.cli.algo07_profile import destination, digest, write_new


def process_identity(pid):
    if pid <= 0:
        raise ValueError('Positive PID required')
    proc = Path('/proc')/str(pid)
    fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, start_ticks=int(fields[19]),
                command=(proc/'cmdline').read_bytes().decode(errors='replace').split('\0')[:-1])


def private_target(identity, root):
    root = root.resolve()
    if not root.is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('Sampling is limited to a private research root')
    if not any(Path(arg).is_absolute() and Path(arg).resolve().is_relative_to(root)
               for arg in identity['command']):
        raise ValueError('Target command does not name the private research root')


def sample(args):
    if not 1 <= args.duration <= 60:
        raise ValueError('Sampling duration must be 1..60 seconds')
    before = process_identity(args.pid)
    private_target(before, args.research_root)
    output = destination(args.output)
    output.mkdir(parents=True, exist_ok=False)
    command = [str(args.sampler.resolve(strict=True)), 'record', '--pid', str(args.pid),
               '--duration', str(args.duration), '--rate', '100', '--nonblocking',
               '--full-filenames', '--format', 'raw', '--output', str(output/'stacks.folded')]
    write_new(output/'launch.json', dict(target=before, command=command,
                                       scope='one child; not its descendants'))
    timed_out = False
    with (output/'sampler.log').open('xb') as log:
        try:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                       timeout=args.duration+15, check=False)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            # run() terminates only the sampler, never the sampled PID.
            code = None
            timed_out = True
    try:
        after = process_identity(args.pid)
    except FileNotFoundError:
        after = None
    same_process = after is None or before['start_ticks'] == after['start_ticks']
    raw = output/'stacks.folded'
    valid_samples = corrupted_lines = 0
    if raw.exists():
        for line in raw.read_bytes().splitlines():
            try:
                text = line.decode('utf-8')
                if text.strip():
                    valid_samples += int(text.rsplit(' ', 1)[1])
            except (UnicodeDecodeError, ValueError, IndexError):
                corrupted_lines += 1
    errors = re.search(r'Errors:\s*(\d+)', (output/'sampler.log').read_text(errors='replace'))
    result = dict(successful_sampling=code == 0 and not timed_out and same_process
                  and valid_samples > 0, sampler_exit_code=code, sampler_timed_out=timed_out,
                  valid_samples=valid_samples, corrupted_lines=corrupted_lines,
                  sampler_read_errors=int(errors[1]) if errors else None,
                  target_exited=after is None, target_identity_unchanged=same_process,
                  raw_sha256=digest(raw) if raw.exists() else None,
                  nonblocking=True, descendant_coverage=False,
                  scientific_parity_checked=False,
                  limitations='Sampling can miss native work and fail to unwind live frames; '
                              'inspect sampler.log for read errors; retain raw bytes.')
    write_new(output/'sampling.json', result)
    return result
