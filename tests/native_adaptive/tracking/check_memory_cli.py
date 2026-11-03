"""Bounded execution/input rejection checks for the native memory adapter."""
import pathlib
import subprocess
import sys
import tempfile


def main():
    binary = pathlib.Path(sys.argv[1]).resolve()
    assert subprocess.run([str(binary)], capture_output=True).returncode == 2
    with tempfile.TemporaryDirectory(prefix='leo-memory-cli-') as directory:
        output = pathlib.Path(directory) / 'associations.json'
        base = ['missing-observations', 'missing-graph', 'missing-tracks', 'missing-tles',
                '-60', '10', '43', '38.5816', '-121.4944', '250', '1', str(output)]
        for index, value in [(4, 'nan'), (5, '0'), (6, '1'), (6, '2001'),
                             (7, '91'), (8, '-181'), (9, '501'), (10, '3')]:
            args = base.copy()
            args[index] = value
            result = subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=10)
            assert result.returncode == 1 and not result.stdout
            assert not output.exists()
        result = subprocess.run([str(binary), *base], capture_output=True, text=True, timeout=10)
        assert result.returncode == 1 and 'cannot open checkpoints' in result.stderr
        assert not output.exists()
    print('memory CLI rejection checks passed')


if __name__ == '__main__':
    main()
