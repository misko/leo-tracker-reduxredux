import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_independent_arrivals_and_explicit_overload(tmp_path):
    binary = tmp_path / "paced"
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-O2",
            "-pthread",
            "-I" + str(ROOT / "native/adaptive/detector"),
            str(ROOT / "native/adaptive/bench/paced.cpp"),
            str(ROOT / "native/adaptive/runtime/runtime.cpp"),
            str(Path(__file__).with_name("fake_detector.cpp")),
            "-o",
            str(binary),
        ],
        check=True,
    )
    iq, template, manifest = (tmp_path / n for n in ("iq", "template", "manifest"))
    iq.write_bytes(bytes(8))
    template.write_bytes(bytes(16))
    manifest.write_text(
        "".join(f"{i}\t750\t120\t120\t{template}\t{template}\t{iq}\t{{}}\n" for i in range(2))
    )
    process = subprocess.run(
        [str(binary), str(manifest), "1", "10", "1", "0"],
        check=True,
        text=True,
        capture_output=True,
        timeout=10,
    )
    rows = [json.loads(line) for line in process.stdout.splitlines()]
    summary = rows[-1]
    assert summary["arrivals"] == 20
    assert summary["completed"] + summary["rejected"] == 20
    assert summary["rejected"] > 0
    assert summary["queue_high_water"] == 1
    assert summary["failed"] == 0
    assert all(r["positive"] == 1 for r in rows[:-1] if r["accepted"])
    manifest.write_text("bad\n")
    assert (
        subprocess.run(
            [str(binary), str(manifest), "1", "1", "1", "0"], capture_output=True
        ).returncode
        == 2
    )
