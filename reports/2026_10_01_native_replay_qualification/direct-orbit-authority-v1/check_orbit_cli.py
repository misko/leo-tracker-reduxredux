"""Exercise the built orbit CLI's rejection boundary without corpus/hardware."""
import pathlib
import subprocess
import sys
import tempfile
import json
import struct


def main():
    binary = pathlib.Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="leo-orbit-cli-") as directory:
        root = pathlib.Path(directory)
        source, output = root / "input.tle", root / "output.states"
        geometry = ["1790590660968615222", "-60", "10", "43"]
        # Valid lengths and IDs reach the identity/trailing-row checks, before
        # propagation. Scientific propagation is tested by test_location.cpp.
        a = "1 12345" + " " * 62
        b = "2 12345" + " " * 62
        cases = [
            ("", geometry),
            ("0\n", geometry),
            ("20001\n", geometry),
            ("1\nshort\nshort\n", geometry),
            (f"1\n{a}\n2 54321{' ' * 62}\n", geometry),
            (f"2\n{a}\n{b}\n{a}\n{b}\n", geometry),
            (f"1\n{a}\n{b}\nextra\n", geometry),
            ("1\n", ["0", "-60", "10", "43"]),
            ("1\n", [geometry[0], "nan", "10", "43"]),
            ("1\n", [geometry[0], "-60", "0", "43"]),
            ("1\n", [geometry[0], "-60", "10", "1"]),
            ("1\n", [geometry[0], "-60", "10", "2001"]),
        ]
        for payload, args in cases:
            source.write_text(payload)
            result = subprocess.run([str(binary), str(source), *args, str(output)],
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == 1, (args, result)
            assert result.stderr.startswith("orbit: "), result.stderr
            assert not result.stdout, result.stdout
            assert not output.exists(), "Rejected input must not publish states"
        source.write_text('1\n'
            '1 44714U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999\n'
            '2 44714  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103\n')
        baseline = subprocess.run([str(binary), str(source), *geometry, str(output)],
            capture_output=True, text=True, check=True, timeout=10)
        loc1 = root / 'authority.loc1'
        site = ['6378.137', '0', '0', '1', '0', '0']
        result = subprocess.run([str(binary), str(source), *geometry, str(loc1), '--loc1-site', *site],
            capture_output=True, text=True, check=True, timeout=10)
        assert json.loads(result.stdout) == json.loads(baseline.stdout)
        raw = loc1.read_bytes()
        assert struct.unpack_from('<5I2d', raw) == (0x31434f4c, 1, 43, 0, 1, -60, 10)
        assert struct.unpack_from('<6d', raw, 36) == tuple(map(float, site))
        assert struct.unpack_from('<i', raw, 84) == (44714,)
        assert raw[88:] == output.read_bytes()
        for invalid in [['nan', *site[1:]], [*site[:3], '0', '0', '0']]:
            rejected = root / 'invalid.loc1'
            result = subprocess.run([str(binary), str(source), *geometry, str(rejected),
                                     '--loc1-site', *invalid], capture_output=True, timeout=10)
            assert result.returncode == 1 and not rejected.exists()
    print(f"orbit CLI rejection tests passed ({len(cases)} cases); LOC1 packaging and site validation passed")


if __name__ == "__main__":
    main()
