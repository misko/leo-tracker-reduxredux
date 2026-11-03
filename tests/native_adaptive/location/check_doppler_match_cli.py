"""CLI boundary tests; optional explicit-path replay against the frozen prototype."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def check_cli(binary):
    observations = (
        "SDP1 1790557997299661326 11200000000 38.5816 -121.4944 250 60 5 30 20 8\n"
        "1\n6 3\n0 0 1\n1 0 1\n2 0 0\n3 0 1\n4 0 1\n5 0 0\n0 0\n2.5 0\n5 0\n"
    )
    catalogue = (
        "1\n"
        "1 44714U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999\n"
        "2 44714  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103\n"
    )
    with tempfile.TemporaryDirectory(prefix="leo-doppler-cli-") as directory:
        observations_path = Path(directory) / "observations.txt"
        catalogue_path = Path(directory) / "catalogue.tle"

        def run(obs, tles, *flags):
            observations_path.write_text(obs)
            catalogue_path.write_text(tles)
            return subprocess.run(
                [str(binary), str(observations_path), str(catalogue_path), *flags],
                capture_output=True, text=True, timeout=10,
            )

        good = run(observations, catalogue)
        assert good.returncode == 0, good.stderr
        output = json.loads(good.stdout)
        assert output["schema"] == "leo-streaming-doppler-result/v1"
        assert output["catalogue_records"] == 1 and output["track_count"] == 1
        assert output["candidate_only"] and not output["global_completeness_claimed"]
        cases = [
            ("", catalogue, ()),
            (observations + "extra\n", catalogue, ()),
            (observations.replace("6 3", "-1 3"), catalogue, ()),
            (observations.replace("0 0 1", "0 0 256", 1), catalogue, ()),
            (observations.replace("60 5 30", "60 0 30"), catalogue, ()),
            (observations, "1\nshort\nshort\n", ()),
            (observations, catalogue + "extra\n", ()),
            (observations, catalogue, ("--unknown",)),
        ]
        for obs, tles, flags in cases:
            bad = run(obs, tles, *flags)
            assert bad.returncode == 1 and bad.stderr and not bad.stdout, bad
    print(f"Doppler matcher CLI tests passed ({len(cases)} rejection cases)")


def check_recorded_replay(binary, report):
    # Explicit local files only: no service, network, QNAP or radio access.
    replay = subprocess.run(
        [str(binary), str(report / "input/observations.txt"), str(report / "input/catalogue.tle")],
        capture_output=True, text=True, check=True, timeout=60,
    )
    actual = json.loads(replay.stdout)
    expected = json.loads((report / "host.json").read_text())
    for key in ("propagation_s", "proposal_s", "refinement_s", "total_s"):
        actual.pop(key)
        expected.pop(key)
    assert actual == expected, "Recorded candidate values or work counters changed"
    count = sum(len(track["hypotheses"]) for track in actual["tracks"])
    print(f"Frozen host replay matched exactly: {len(actual['tracks'])} tracks, {count} candidates")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: check_doppler_match_cli.py BINARY [RECORDED_REPORT_DIRECTORY]")
    executable = Path(sys.argv[1]).resolve()
    check_cli(executable)
    if len(sys.argv) == 3:
        check_recorded_replay(executable, Path(sys.argv[2]).resolve())
