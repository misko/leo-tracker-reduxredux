"""Compare physical ARM tracking with the fresh-native host export."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEPLOYMENT = HERE.parents[1]
NATIVE = DEPLOYMENT / "ds9/corrected-full-replay-v1/full-public-c3-c4"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    actual = HERE / "tracks.tsv"
    expected = NATIVE / "tracks.tsv"
    timing = json.loads((HERE / "physical.time.json").read_text())
    exact = actual.read_bytes() == expected.read_bytes()
    count = sum(line.startswith("TRACK\t") for line in actual.read_text().splitlines())
    result = {
        "schema": "leo-corrected-native-arm-tracking/v1",
        "status": "pass" if exact and count == 64 and timing["exit_code"] == 0 else "fail",
        "scope": "physical ARM tracking of host-computed corrected native DS9 observations",
        "input_sha256": digest(NATIVE / "candidates.tsv"),
        "host_output_sha256": digest(expected),
        "arm_output_sha256": digest(actual),
        "byte_identical": exact,
        "tracks": count,
        "timing": timing,
        "detector_executed_on_arm_in_this_test": False,
        "location_executed_in_this_test": False,
        "continuous_realtime_qualified": False,
    }
    (HERE / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
